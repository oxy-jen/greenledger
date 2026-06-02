from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import uuid

db = SQLAlchemy()

class Participant(db.Model):
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    record_number = db.Column(db.String(20), unique=True, nullable=False) # GL-2026-000247
    full_name = db.Column(db.String(100), nullable=False)
    role = db.Column(db.String(50), nullable=False) # e.g., "ICT Student"
    tree_species = db.Column(db.String(50), nullable=False) # e.g., "Moringa"
    quantity = db.Column(db.Integer, nullable=False) # e.g., 25
    planting_zone = db.Column(db.String(100), nullable=False)
    photo_path = db.Column(db.String(200), nullable=True)
    latitude = db.Column(db.Float, nullable=True)
    longitude = db.Column(db.Float, nullable=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    status = db.Column(db.String(20), default='Pending') # Pending, Verified, Rejected
    is_vip = db.Column(db.Boolean, default=False) # Priority Participant
    
    # Environmental Impact Calculated Field
    co2_saved_kg = db.Column(db.Float, default=0.0)

    def __repr__(self):
        return f'<Participant {self.record_number}>'