#!/usr/bin/env python3
import os
import sys
import subprocess
import shutil
import threading
import time
from pathlib import Path

# Try importing dotenv
try:
    import dotenv
except ImportError:
    print("Error: python-dotenv is not installed in the current environment.")
    print("Please run: uv sync or pip install python-dotenv")
    sys.exit(1)

def find_repo_root():
    # Start at the script's directory and walk up until we find .git or pyproject.toml
    current = Path(__file__).resolve().parent
    for _ in range(5):
        if (current / ".git").exists() or (current / "pyproject.toml").exists():
            return current
        current = current.parent
    return Path.cwd()

def verify_aws(env):
    aws_profile = env.get("AWS_PROFILE")
    if not aws_profile:
        print("[-] AWS_PROFILE is not set in environment or .env file.")
        print("[-] Proceeding without verifying AWS profile.")
        return True

    print(f"[*] Found AWS_PROFILE={aws_profile}. Verifying AWS credentials...")
    
    # Try running sts get-caller-identity
    sts_cmd = ["aws", "sts", "get-caller-identity", "--profile", aws_profile]
    try:
        # Run with the loaded env so any AWS env vars are present
        subprocess.run(sts_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True, env=env)
        print("[+] AWS authentication verified successfully.")
        return True
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        if isinstance(e, FileNotFoundError):
            print("[-] aws CLI command not found. Cannot verify AWS session.")
            return False
        
        print("[-] AWS authentication failed. Attempting AWS SSO login...")
        login_cmd = ["aws", "sso", "login", "--profile", aws_profile]
        try:
            subprocess.run(login_cmd, check=True, env=env)
            print("[+] AWS SSO login completed successfully. Verifying again...")
            subprocess.run(sts_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True, env=env)
            print("[+] AWS authentication verified successfully.")
            return True
        except subprocess.CalledProcessError:
            print("[-] AWS SSO login or subsequent verification failed.")
            return False

def verify_stripe():
    print("[*] Checking for Stripe CLI...")
    if not shutil.which("stripe"):
        print("[-] Error: stripe CLI not found in PATH.")
        print("[-] Please install the Stripe CLI (e.g., 'brew install stripe/stripe-cli/stripe') and authenticate.")
        return False
    print("[+] Stripe CLI is installed.")
    return True

def stream_output(pipe, prefix):
    try:
        for line in iter(pipe.readline, ''):
            if not line:
                break
            sys.stdout.write(f"{prefix} {line}")
            sys.stdout.flush()
    except Exception:
        pass
    finally:
        try:
            pipe.close()
        except Exception:
            pass

def main():
    repo_root = find_repo_root()
    env_path = repo_root / ".env"
    
    if env_path.exists():
        print(f"[*] Loading environment variables from {env_path}")
        dotenv.load_dotenv(dotenv_path=env_path)
    else:
        print(f"[-] No .env file found at {env_path}")
    
    # Prepare custom env dictionary (merging os.environ and loaded env)
    # python-dotenv load_dotenv already populates os.environ, so we can just use os.environ.copy()
    run_env = os.environ.copy()
    # Force python unbuffered output so we get live logs from flask
    run_env["PYTHONUNBUFFERED"] = "1"
    
    # Verify AWS & Stripe CLI
    verify_aws(run_env)
    
    if not verify_stripe():
        sys.exit(1)
        
    # Determine flask cmd
    if shutil.which("uv"):
        flask_cmd = ["uv", "run", "flask", "--app", "app", "--debug", "run", "--port", "5001"]
    else:
        flask_cmd = ["flask", "--app", "app", "--debug", "run", "--port", "5001"]
        
    stripe_cmd = ["stripe", "listen", "--forward-to", "localhost:5001/api/v1/webhooks/stripe"]
    
    print("\n[*] Starting Flask Dev Server and Stripe Listener...")
    print(f"[*] Flask command: {' '.join(flask_cmd)}")
    print(f"[*] Stripe command: {' '.join(stripe_cmd)}")
    print("[*] Press Ctrl+C to stop both servers.\n")
    
    flask_proc = None
    stripe_proc = None
    threads = []
    
    try:
        # Start Flask
        flask_proc = subprocess.Popen(
            flask_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            cwd=str(repo_root),
            env=run_env
        )
        
        # Start Stripe
        stripe_proc = subprocess.Popen(
            stripe_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            cwd=str(repo_root),
            env=run_env
        )
        
        # Start threads to stream output
        t1 = threading.Thread(target=stream_output, args=(flask_proc.stdout, "\033[36m[Flask]\033[0m"))
        t2 = threading.Thread(target=stream_output, args=(flask_proc.stderr, "\033[36m[Flask]\033[0m"))
        t3 = threading.Thread(target=stream_output, args=(stripe_proc.stdout, "\033[35m[Stripe]\033[0m"))
        t4 = threading.Thread(target=stream_output, args=(stripe_proc.stderr, "\033[35m[Stripe]\033[0m"))
        
        for t in [t1, t2, t3, t4]:
            t.daemon = True
            t.start()
            threads.append(t)
            
        # Monitor processes
        while True:
            flask_exit = flask_proc.poll()
            stripe_exit = stripe_proc.poll()
            
            if flask_exit is not None:
                print(f"\n[-] Flask process terminated unexpectedly with exit code {flask_exit}.")
                break
            if stripe_exit is not None:
                print(f"\n[-] Stripe process terminated unexpectedly with exit code {stripe_exit}.")
                break
                
            time.sleep(0.5)
            
    except KeyboardInterrupt:
        print("\n[*] Stopping development servers gracefully...")
    finally:
        # Terminate processes
        for proc, name in [(flask_proc, "Flask"), (stripe_proc, "Stripe")]:
            if proc and proc.poll() is None:
                print(f"[*] Terminating {name} process...")
                try:
                    proc.terminate()
                except Exception as e:
                    print(f"[-] Failed to terminate {name}: {e}")
                    
        # Give them a few seconds to exit, then kill if needed
        for _ in range(6):
            flask_done = flask_proc is None or flask_proc.poll() is not None
            stripe_done = stripe_proc is None or stripe_proc.poll() is not None
            if flask_done and stripe_done:
                break
            time.sleep(0.5)
            
        for proc, name in [(flask_proc, "Flask"), (stripe_proc, "Stripe")]:
            if proc and proc.poll() is None:
                print(f"[!] {name} did not exit. Killing it...")
                try:
                    proc.kill()
                except Exception as e:
                    print(f"[-] Failed to kill {name}: {e}")
                    
        print("[+] Dev environment shut down successfully.")

if __name__ == "__main__":
    main()
