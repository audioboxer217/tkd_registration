from datetime import datetime

from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import Numeric, String, Text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.types import JSON

db = SQLAlchemy()


class School(db.Model):
    """Reference table for schools/clubs."""
    __tablename__ = "schools"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(String(200), nullable=False, unique=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    coaches = db.relationship("Coach", back_populates="school", cascade="all, delete-orphan")
    competitors = db.relationship("Competitor", back_populates="school", cascade="all, delete-orphan")

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

    @classmethod
    def get_or_create(cls, name: str) -> "tuple[School | None, bool]":
        """Return (school, is_new). is_new is True when the school was just inserted.

        Flushes (but does not commit) when a new school is created.
        Returns (None, False) when name is empty/None.
        Handles concurrent inserts (e.g. parallel Lambda invocations) by catching
        IntegrityError on the unique-name constraint and re-querying.
        """
        if not name:
            return None, False
        school = cls.query.filter_by(name=name).first()
        if school is not None:
            return school, False
        school = cls(name=name)
        db.session.add(school)
        try:
            db.session.flush()
            return school, True
        except IntegrityError:
            db.session.rollback()
            return cls.query.filter_by(name=name).first(), False

    @classmethod
    def all_names(cls) -> list:
        """Return all school names sorted alphabetically."""
        return [s.name for s in cls.query.order_by(cls.name).all()]


class Coach(db.Model):
    """Coach registration."""
    __tablename__ = "coaches"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    full_name = db.Column(String(200), nullable=False)
    email = db.Column(String(200), nullable=False, index=True)
    phone = db.Column(String(20))
    school_id = db.Column(db.Integer, db.ForeignKey("schools.id"), nullable=False)
    img_filename = db.Column(String(200))
    # Coaches do not go through a Stripe checkout flow; payment fields are on Competitor only.
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    school = db.relationship("School", back_populates="coaches")
    competitors = db.relationship("Competitor", back_populates="coach_rel")

    def to_dict(self):
        return {
            "id": self.id,
            "full_name": self.full_name,
            "email": self.email,
            "phone": self.phone,
            "school_id": self.school_id,
            "school": self.school.name if self.school else None,
            "reg_type": "coach",
            "img_filename": self.img_filename,
            # Competitor form-specific fields (empty for coaches)
            "parent": None,
            "birthdate": None,
            "age": None,
            "gender": None,
            "weight": None,
            "height": None,
            "belt_rank": None,
            "events": [],
            "poomsae_form": None,
            "wc_poomsae_form": None,
            "pair_poomsae_form": None,
            "team_poomsae_form": None,
            "family_poomsae_form": None,
            "medical_contacts": None,
            "medical_conditions": [],
            "allergies": [],
            "medications": [],
            "tshirt": None,
            "coach_id": None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    @classmethod
    def find_by_name_and_school(cls, name: str, school_id: int) -> "Coach | None":
        """Look up a coach by exact name and school_id. Returns None if not found."""
        if not name or not school_id:
            return None
        return cls.query.filter_by(full_name=name, school_id=school_id).first()


class Competitor(db.Model):
    """Competitor registration."""
    __tablename__ = "competitors"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)

    # Core fields
    full_name = db.Column(String(200), nullable=False)
    email = db.Column(String(200), nullable=False, index=True)
    phone = db.Column(String(20))
    school_id = db.Column(db.Integer, db.ForeignKey("schools.id"), nullable=False)
    coach_id = db.Column(db.Integer, db.ForeignKey("coaches.id"), nullable=True)

    # Competitor-specific fields
    parent = db.Column(String(200))
    birthdate = db.Column(String(10))  # stored as MM/DD/YYYY string to match form data
    age = db.Column(db.Integer)
    gender = db.Column(String(1))
    weight = db.Column(Numeric(6, 1))
    height = db.Column(db.Integer)  # total inches
    belt_rank = db.Column(String(50))

    # Events (comma-separated list matching existing format)
    events = db.Column(Text)

    # Poomsae form selections
    poomsae_form = db.Column(String(100))
    wc_poomsae_form = db.Column(String(100))
    pair_poomsae_form = db.Column(String(100))
    team_poomsae_form = db.Column(String(100))
    family_poomsae_form = db.Column(String(100))

    # Medical info (stored as JSON arrays)
    medical_contacts = db.Column(Text)
    medical_conditions = db.Column(JSON)
    allergies = db.Column(JSON)
    medications = db.Column(JSON)

    # Optional feature fields
    img_filename = db.Column(String(200))  # ENABLE_BADGES
    tshirt = db.Column(String(20))  # little dragon t-shirt size

    # Payment
    status = db.Column(String(20), nullable=False, default="pending")
    checkout_session_id = db.Column(String(100), index=True)  # Stripe Checkout Session ID
    payment_intent = db.Column(String(100))

    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    school = db.relationship("School", back_populates="competitors")
    coach_rel = db.relationship("Coach", back_populates="competitors")

    def to_dict(self):
        """Return a JSON-serializable dict representation."""
        return {
            "id": self.id,
            "full_name": self.full_name,
            "email": self.email,
            "phone": self.phone,
            "school": self.school.name if self.school else None,
            "school_id": self.school_id,
            "coach": self.coach_rel.full_name if self.coach_rel else None,
            "coach_id": self.coach_id,
            "parent": self.parent,
            "birthdate": self.birthdate,
            "age": self.age,
            "gender": self.gender,
            "weight": float(self.weight) if self.weight is not None else None,
            "height": self.height,
            "belt_rank": self.belt_rank,
            "events": self.events.split(",") if self.events else [],
            "poomsae_form": self.poomsae_form,
            "wc_poomsae_form": self.wc_poomsae_form,
            "pair_poomsae_form": self.pair_poomsae_form,
            "team_poomsae_form": self.team_poomsae_form,
            "family_poomsae_form": self.family_poomsae_form,
            "medical_contacts": self.medical_contacts,
            "medical_conditions": self.medical_conditions or [],
            "allergies": self.allergies or [],
            "medications": self.medications or [],
            "img_filename": self.img_filename,
            "tshirt": self.tshirt,
            "checkout_session_id": self.checkout_session_id,
            "payment_intent": self.payment_intent,
            "status": self.status,
            "reg_type": "competitor",
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    @classmethod
    def find_by_checkout_session(cls, session_id: str) -> "Competitor | None":
        """Return the competitor whose Stripe checkout session matches session_id."""
        return cls.query.filter_by(checkout_session_id=session_id).first()

    @classmethod
    def eligible(cls, status: "str | None" = "complete") -> list:
        """Return competitors filtered by payment status.

        Pass status=None to return all competitors regardless of status.
        """
        if status is None:
            return cls.query.all()
        return cls.query.filter_by(status=status).all()


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------


def age_group_for(age) -> str:
    """Map an integer age to its competition age-group name."""
    age_groups = {
        "too_young": list(range(0, 4)),
        "dragon": [4, 5, 6, 7],
        "tiger": [8, 9],
        "youth": [10, 11],
        "cadet": [12, 13, 14],
        "junior": [15, 16],
        "senior": list(range(17, 33)),
        "ultra": list(range(33, 100)),
    }
    return next((group for group, ages in age_groups.items() if int(age) in ages), "too_old")


def entry_exists(full_name: str, school_id: int, reg_type: str) -> bool:
    """Return True when a competitor or coach with this name/school already exists."""
    model = Competitor if reg_type == "competitor" else Coach
    return model.query.filter_by(full_name=full_name, school_id=school_id).first() is not None


def find_entry_by_id(entry_id) -> "Competitor | Coach | None":
    """Look up a registration by integer ID from Competitor or Coach tables.

    Accepts int or string; returns None if the ID is non-numeric or not found.
    """
    try:
        reg_id = int(entry_id)
    except (ValueError, TypeError):
        return None
    reg = db.session.get(Competitor, reg_id)
    if reg is not None:
        return reg
    return db.session.get(Coach, reg_id)


def create_entry(body: dict) -> tuple:
    """Validate and persist a registration record to the database.

    Performs school resolution, duplicate detection, and creates the appropriate
    Competitor or Coach record.  The session is flushed (not committed) on success
    so the caller can attach additional fields (e.g. checkout_session_id) before
    committing.

    Returns:
        (reg, None, None, new_school_name_or_none) on success – reg is flushed but not yet committed.
        (None, error_msg, code, None)              on failure – session is rolled back.
    """
    school, is_new = School.get_or_create(body.get("school"))
    if school is None:
        db.session.rollback()
        return None, "School is required", 422, None

    if entry_exists(body["full_name"], school.id, body["reg_type"]):
        db.session.rollback()
        return None, f"Duplicate registration for {body['full_name']}", 409, None

    if body["reg_type"] == "competitor":
        coach_name = (body.get("coach") or "").strip() or None
        coach_id = None
        if coach_name:
            linked_coach = Coach.find_by_name_and_school(coach_name, school.id)
            coach_id = linked_coach.id if linked_coach else None
        reg = Competitor(
            full_name=body["full_name"],
            email=body["email"],
            phone=body.get("phone"),
            school_id=school.id,
            coach_id=coach_id,
            parent=body.get("parent"),
            birthdate=body.get("birthdate"),
            age=body.get("age"),
            gender=body.get("gender"),
            weight=body.get("weight"),
            height=body.get("height"),
            belt_rank=body.get("belt_rank"),
            events=",".join(body.get("events", [])),
            poomsae_form=body.get("poomsae_form"),
            wc_poomsae_form=body.get("wc_poomsae_form"),
            pair_poomsae_form=body.get("pair_poomsae_form"),
            team_poomsae_form=body.get("team_poomsae_form"),
            family_poomsae_form=body.get("family_poomsae_form"),
            medical_contacts=body.get("medical_contacts"),
            medical_conditions=body.get("medical_conditions", []),
            allergies=body.get("allergies", []),
            medications=body.get("medications", []),
            img_filename=body.get("img_filename"),
            tshirt=body.get("tshirt"),
            status="pending",
        )
    else:
        reg = Coach(
            full_name=body["full_name"],
            email=body["email"],
            phone=body.get("phone"),
            school_id=school.id,
            img_filename=body.get("img_filename"),
        )

    db.session.add(reg)
    db.session.flush()
    return reg, None, None, school.name if is_new else None


def init_db(app):
    """Bind SQLAlchemy to the Flask app."""
    db.init_app(app)
