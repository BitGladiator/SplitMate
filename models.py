from extensions import db
from datetime import datetime, timezone

class Friend(db.Model):
    __tablename__ = 'friends'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    # Relationships
    payments_made = db.relationship('Settlement', back_populates='payer', foreign_keys='Settlement.payer_id')
    payments_received = db.relationship('Settlement', back_populates='payee', foreign_keys='Settlement.payee_id')

    def __repr__(self):
        return f"<Friend {self.name}>"


class Expense(db.Model):
    __tablename__ = 'expenses'
    
    id = db.Column(db.Integer, primary_key=True)
    description = db.Column(db.String(200), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    paid_by_id = db.Column(db.Integer, db.ForeignKey('friends.id'), nullable=False)
    split_between = db.Column(db.String(300), nullable=False)
    timestamp = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    is_settled = db.Column(db.Boolean, default=False)

    # Main relationship (for template)
    paid_by = db.relationship('Friend', backref='expenses_paid', foreign_keys=[paid_by_id])

    # Alias for backward compatibility (for dashboard)
    @property
    def payer(self):
        return self.paid_by

    def split_with(self):
        """Returns list of Friend objects who share this expense"""
        if not self.split_between:
            return []
        friend_ids = [int(fid) for fid in self.split_between.split(',') if fid.strip().isdigit()]
        return Friend.query.filter(Friend.id.in_(friend_ids)).all()

    def __repr__(self):
        return f"<Expense ₹{self.amount} for {self.description}>"


class Settlement(db.Model):
    __tablename__ = 'settlements'
    
    id = db.Column(db.Integer, primary_key=True)
    payer_id = db.Column(db.Integer, db.ForeignKey('friends.id'), nullable=False)
    payee_id = db.Column(db.Integer, db.ForeignKey('friends.id'), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    timestamp = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    expense_id = db.Column(db.Integer, db.ForeignKey('expenses.id'), nullable=True)

    # Relationships
    payer = db.relationship('Friend', back_populates='payments_made', foreign_keys=[payer_id])
    payee = db.relationship('Friend', back_populates='payments_received', foreign_keys=[payee_id])
    expense = db.relationship('Expense', backref='settlements')

    def __repr__(self):
        return f"<Settlement: {self.payer.name} → {self.payee.name} ₹{self.amount}>"
