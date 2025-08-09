from flask import Flask, render_template, request, redirect, url_for, flash
import os
from models import Settlement, Friend, Expense
from extensions import db
from sqlalchemy import extract
from collections import defaultdict
from datetime import datetime
from flask_wtf import CSRFProtect 

app = Flask(__name__)

# --- App Configuration ---
basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'splitmate.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.secret_key = "your_secret_key_here"  # IMPORTANT: Change this to a strong secret key!

# --- Initialize Extensions ---
db.init_app(app)
csrf = CSRFProtect(app)  # Enable CSRF Protection for all POST, PUT, DELETE methods

@app.route('/')
def index():
    return render_template('index.html')


@app.route('/dashboard')
def dashboard():
    expenses = Expense.query.order_by(Expense.timestamp.desc()).all()

    balances = defaultdict(float)
    you_owe = 0
    you_are_owed = 0

    for expense in expenses:
        split_friends = expense.split_with()
        payer = expense.payer
        total_amount = expense.amount
        split_count = len(split_friends)
        share = total_amount / split_count if split_count > 0 else 0

        for friend in split_friends:
            if friend.id != payer.id:
                key = f"{friend.name} -> {payer.name}"
                balances[key] += round(share, 2)
                if payer.id == 1:
                    you_are_owed += round(share, 2)
                if friend.id == 1:
                    you_owe += round(share, 2)

    settlements = Settlement.query.all()
    for settlement in settlements:
        key = f"{settlement.payer.name} -> {settlement.payee.name}"
        if key in balances:
            balances[key] -= settlement.amount
            if balances[key] <= 0:
                del balances[key]

    total_spent = sum(exp.amount for exp in expenses)
    unsettled_count = len([b for b in balances.values() if b > 0])

    return render_template(
        'dashboard.html',
        expenses=expenses,
        balances=balances,
        total_spent=total_spent,
        you_owe=you_owe,
        you_are_owed=you_are_owed,
        unsettled_count=unsettled_count
    )


@app.route('/add', methods=['GET', 'POST'])
def add_expense():
    friends = Friend.query.all()
    if request.method == 'POST':
        description = request.form['description']
        amount = float(request.form['amount'])
        paid_by = int(request.form['paid_by'])
        split_between = request.form.getlist('split_between')

        split_str = ",".join(split_between)

        new_expense = Expense(
            description=description,
            amount=amount,
            paid_by_id=paid_by,
            split_between=split_str,
            timestamp=datetime.now()
        )
        db.session.add(new_expense)
        db.session.commit()
        flash('Expense added successfully!', 'success')
        return redirect(url_for('dashboard'))

    return render_template('add_expense.html', friends=friends)


@app.route('/history')
def history():
    expenses = Expense.query.order_by(Expense.timestamp.desc()).all()
    settlements = Settlement.query.order_by(Settlement.timestamp.desc()).all()
    return render_template('history.html', expenses=expenses, settlements=settlements)


@app.route('/settle', methods=['GET', 'POST'])
def settle():
    friends = Friend.query.all()

    if request.method == 'POST':
        payer_id = int(request.form['payer'])
        payee_id = int(request.form['payee'])
        amount = float(request.form['amount'])

        if payer_id != payee_id:
            settlement = Settlement(
                payer_id=payer_id,
                payee_id=payee_id,
                amount=amount,
                timestamp=datetime.now()
            )
            db.session.add(settlement)
            db.session.commit()
            flash('Settlement recorded successfully!', 'success')
            return redirect(url_for('dashboard'))

    return render_template('settle.html', friends=friends)


@app.route('/summary')
def monthly_summary():
    now = datetime.now()
    month = int(request.args.get('month', now.month))
    year = int(request.args.get('year', now.year))

    expenses = Expense.query.filter(
        extract('month', Expense.timestamp) == month,
        extract('year', Expense.timestamp) == year
    ).all()

    settlements = Settlement.query.filter(
        extract('month', Settlement.timestamp) == month,
        extract('year', Settlement.timestamp) == year
    ).all()

    summary = {}
    friends = Friend.query.all()

    for friend in friends:
        summary[friend.id] = {
            'name': friend.name,
            'paid': 0,
            'owed': 0,
            'received': 0
        }

    for exp in expenses:
        split_friends = exp.split_with()
        per_head = exp.amount / len(split_friends) if split_friends else 0
        summary[exp.paid_by.id]['paid'] += exp.amount

        for f in split_friends:
            summary[f.id]['owed'] += per_head

    for s in settlements:
        summary[s.payer_id]['paid'] += s.amount
        summary[s.payee_id]['received'] += s.amount

    for data in summary.values():
        data['net_balance'] = round(data['paid'] + data['received'] - data['owed'], 2)

    return render_template(
        'monthly_summary.html',
        summary=summary.values(),
        month=month,
        year=year,
        current_month=now.month,
        current_year=now.year
    )


@app.route('/friends', methods=['GET', 'POST'])
def friends():
    if request.method == 'POST':
        name = request.form['name']
        if name:
            friend = Friend(name=name)
            db.session.add(friend)
            db.session.commit()
            flash('Friend added successfully!', 'success')
    friends = Friend.query.all()
    return render_template('friends.html', friends=friends)


@app.route('/delete_friend/<int:friend_id>', methods=['POST'])
def delete_friend(friend_id):
    friend = Friend.query.get_or_404(friend_id)
    db.session.delete(friend)
    db.session.commit()
    flash('Friend deleted successfully!', 'success')
    return redirect(url_for('friends'))


@app.route('/delete_expense/<int:expense_id>', methods=['POST'])
def delete_expense(expense_id):
    expense = Expense.query.get_or_404(expense_id)

    # Delete any linked settlements first to maintain DB integrity
    for settlement in expense.settlements:
        db.session.delete(settlement)

    db.session.delete(expense)
    db.session.commit()

    flash('Expense deleted successfully.', 'success')
    return redirect(url_for('dashboard'))


@app.route('/delete_settlement/<int:settlement_id>', methods=['POST'])
def delete_settlement(settlement_id):
    settlement = Settlement.query.get_or_404(settlement_id)
    db.session.delete(settlement)
    db.session.commit()
    flash('Settlement deleted successfully.', 'success')
    return redirect(request.referrer or url_for('dashboard'))


if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)
