from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, make_response
import os
from models import Settlement, Friend, Expense
from extensions import db
from sqlalchemy import extract, func
from collections import defaultdict
from datetime import datetime, timedelta
from flask_wtf import CSRFProtect 
import json
import csv
import io
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter, A4
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch

# 2. CREATE AND CONFIGURE APP
app = Flask(__name__)

basedir = os.path.abspath(os.path.dirname(__file__))

# Use environment variable for database URL, fallback to data directory
database_url = os.environ.get('DATABASE_URL')
if not database_url:
    # Ensure data directory exists
    data_dir = os.path.join(basedir, 'data')
    os.makedirs(data_dir, exist_ok=True)
    database_url = f'sqlite:///{os.path.join(data_dir, "splitmate.db")}'

app.config['SQLALCHEMY_DATABASE_URI'] = database_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.secret_key = os.environ.get('SECRET_KEY', "your_secret_key_here")

# Ensure data directory exists
data_dir = os.path.join(basedir, 'data')
if not os.path.exists(data_dir):
    os.makedirs(data_dir, exist_ok=True)

# 3. INITIALIZE EXTENSIONS (right after config)
db.init_app(app)
csrf = CSRFProtect(app)

@app.route('/')
def index():
    return render_template('index.html')


@app.route('/dashboard')
def dashboard():
    expenses = Expense.query.order_by(Expense.timestamp.desc()).all() # Get all expenses

    balances = defaultdict(float) # Initialize a dictionary to store balances
    you_owe = 0 # Initialize a variable to store the amount you owe
    you_are_owed = 0 # Initialize a variable to store the amount you are owed

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
    total_friends = Friend.query.count()
    total_expenses = len(expenses)
    unsettled_count = len([b for b in balances.values() if b > 0])

    return render_template(
        'dashboard.html',
        expenses=expenses,
        balances=balances,
        total_spent=total_spent,
        total_friends=total_friends,
        total_expenses=total_expenses,
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


@app.route('/analytics')
def analytics():
    """Analytics dashboard with charts"""
    return render_template('analytics.html')


@app.route('/api/chart-data')
def chart_data():
    """API endpoint for chart data"""
    chart_type = request.args.get('type', 'monthly_spending')
    
    if chart_type == 'monthly_spending':
        return get_monthly_spending_data()
    elif chart_type == 'friend_spending':
        return get_friend_spending_data()
    elif chart_type == 'category_breakdown':
        return get_category_breakdown_data()
    elif chart_type == 'settlement_trends':
        return get_settlement_trends_data()
    
    return jsonify({'error': 'Invalid chart type'})


def get_monthly_spending_data():
    """Get monthly spending data for the last 12 months"""
    end_date = datetime.now()
    start_date = end_date - timedelta(days=365)
    
    monthly_data = []
    current_date = start_date.replace(day=1)
    
    while current_date <= end_date:
        expenses = Expense.query.filter(
            extract('month', Expense.timestamp) == current_date.month,
            extract('year', Expense.timestamp) == current_date.year
        ).all()
        
        total_amount = sum(exp.amount for exp in expenses)
        
        monthly_data.append({
            'month': current_date.strftime('%b %Y'),
            'amount': round(total_amount, 2),
            'expenses_count': len(expenses)
        })
        
        # Move to next month
        if current_date.month == 12:
            current_date = current_date.replace(year=current_date.year + 1, month=1)
        else:
            current_date = current_date.replace(month=current_date.month + 1)
    
    return jsonify({'data': monthly_data})


def get_friend_spending_data():
    """Get spending data by friend"""
    friends = Friend.query.all()
    friend_data = []
    
    for friend in friends:
        paid_expenses = Expense.query.filter_by(paid_by_id=friend.id).all()
        total_paid = sum(exp.amount for exp in paid_expenses)
        
        # Calculate total owed by this friend
        all_expenses = Expense.query.all()
        total_owed = 0
        for expense in all_expenses:
            split_friends = expense.split_with()
            if friend in split_friends:
                share = expense.amount / len(split_friends)
                total_owed += share
        
        # Calculate settlements
        settlements_paid = Settlement.query.filter_by(payer_id=friend.id).all()
        settlements_received = Settlement.query.filter_by(payee_id=friend.id).all()
        
        total_settled_paid = sum(s.amount for s in settlements_paid)
        total_settled_received = sum(s.amount for s in settlements_received)
        
        net_balance = total_paid + total_settled_received - total_owed - total_settled_paid
        
        friend_data.append({
            'name': friend.name,
            'total_paid': round(total_paid, 2),
            'total_owed': round(total_owed, 2),
            'net_balance': round(net_balance, 2),
            'expenses_count': len(paid_expenses)
        })
    
    return jsonify({'data': friend_data})


def get_category_breakdown_data():
    """Get expense breakdown by categories (based on keywords in description)"""
    expenses = Expense.query.all()
    categories = {
        'Food & Dining': ['food', 'restaurant', 'dinner', 'lunch', 'breakfast', 'meal', 'pizza', 'burger', 'cafe'],
        'Transportation': ['uber', 'taxi', 'bus', 'train', 'flight', 'gas', 'fuel', 'parking'],
        'Entertainment': ['movie', 'cinema', 'game', 'party', 'club', 'concert', 'show'],
        'Shopping': ['shopping', 'clothes', 'electronics', 'amazon', 'store'],
        'Bills & Utilities': ['electricity', 'water', 'internet', 'phone', 'rent', 'utility'],
        'Healthcare': ['doctor', 'medicine', 'hospital', 'pharmacy', 'medical'],
        'Other': []
    }
    
    category_totals = {cat: 0 for cat in categories.keys()}
    
    for expense in expenses:
        description_lower = expense.description.lower()
        categorized = False
        
        for category, keywords in categories.items():
            if category == 'Other':
                continue
            for keyword in keywords:
                if keyword in description_lower:
                    category_totals[category] += expense.amount
                    categorized = True
                    break
            if categorized:
                break
        
        if not categorized:
            category_totals['Other'] += expense.amount
    
    # Convert to list format for charts
    category_data = [
        {'category': cat, 'amount': round(amount, 2)} 
        for cat, amount in category_totals.items() 
        if amount > 0
    ]
    
    return jsonify({'data': category_data})


def get_settlement_trends_data():
    """Get settlement trends over time"""
    settlements = Settlement.query.order_by(Settlement.timestamp).all()
    
    # Group by month
    monthly_settlements = defaultdict(lambda: {'amount': 0, 'count': 0})
    
    for settlement in settlements:
        month_key = settlement.timestamp.strftime('%Y-%m')
        monthly_settlements[month_key]['amount'] += settlement.amount
        monthly_settlements[month_key]['count'] += 1
    
    # Convert to list and sort
    settlement_data = []
    for month_key in sorted(monthly_settlements.keys()):
        data = monthly_settlements[month_key]
        settlement_data.append({
            'month': datetime.strptime(month_key, '%Y-%m').strftime('%b %Y'),
            'amount': round(data['amount'], 2),
            'count': data['count']
        })
    
    return jsonify({'data': settlement_data})


@app.route('/export')
def export():   # <-- now the endpoint is "export"
    """Export options page"""
    return render_template('export.html')


@app.route('/export/csv')
def export_csv():
    """Export expenses and settlements to CSV"""
    export_type = request.args.get('type', 'expenses')
    
    output = io.StringIO()
    
    if export_type == 'expenses':
        expenses = Expense.query.order_by(Expense.timestamp.desc()).all()
        writer = csv.writer(output)
        
        # Headers
        writer.writerow(['Date', 'Description', 'Amount', 'Paid By', 'Split Between', 'Share Per Person'])
        
        # Data
        for expense in expenses:
            split_friends = expense.split_with()
            split_names = ', '.join([f.name for f in split_friends])
            share_per_person = expense.amount / len(split_friends) if split_friends else 0
            
            writer.writerow([
                expense.timestamp.strftime('%Y-%m-%d %H:%M:%S'),
                expense.description,
                f"₹{expense.amount:.2f}",
                expense.paid_by.name,
                split_names,
                f"₹{share_per_person:.2f}"
            ])
        
        filename = f'expenses_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'
    
    elif export_type == 'settlements':
        settlements = Settlement.query.order_by(Settlement.timestamp.desc()).all()
        writer = csv.writer(output)
        
        # Headers
        writer.writerow(['Date', 'From', 'To', 'Amount', 'Type'])
        
        # Data
        for settlement in settlements:
            writer.writerow([
                settlement.timestamp.strftime('%Y-%m-%d %H:%M:%S'),
                settlement.payer.name,
                settlement.payee.name,
                f"₹{settlement.amount:.2f}",
                'Settlement'
            ])
        
        filename = f'settlements_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'
    
    elif export_type == 'balances':
        # Calculate current balances
        expenses = Expense.query.all()
        settlements = Settlement.query.all()
        friends = Friend.query.all()
        
        # Calculate balances for each friend
        balances = {}
        for friend in friends:
            balances[friend.id] = {
                'name': friend.name,
                'total_paid': 0,
                'total_owed': 0,
                'settlements_made': 0,
                'settlements_received': 0
            }
        
        # Process expenses
        for expense in expenses:
            split_friends = expense.split_with()
            share_per_person = expense.amount / len(split_friends) if split_friends else 0
            
            balances[expense.paid_by_id]['total_paid'] += expense.amount
            
            for friend in split_friends:
                balances[friend.id]['total_owed'] += share_per_person
        
        # Process settlements
        for settlement in settlements:
            balances[settlement.payer_id]['settlements_made'] += settlement.amount
            balances[settlement.payee_id]['settlements_received'] += settlement.amount
        
        writer = csv.writer(output)
        writer.writerow(['Friend', 'Total Paid', 'Total Owed', 'Settlements Made', 'Settlements Received', 'Net Balance'])
        
        for balance_data in balances.values():
            net_balance = (balance_data['total_paid'] + balance_data['settlements_received'] - 
                          balance_data['total_owed'] - balance_data['settlements_made'])
            
            writer.writerow([
                balance_data['name'],
                f"₹{balance_data['total_paid']:.2f}",
                f"₹{balance_data['total_owed']:.2f}",
                f"₹{balance_data['settlements_made']:.2f}",
                f"₹{balance_data['settlements_received']:.2f}",
                f"₹{net_balance:.2f}"
            ])
        
        filename = f'balances_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'
    
    # Create response
    response = make_response(output.getvalue())
    response.headers['Content-Disposition'] = f'attachment; filename={filename}'
    response.headers['Content-type'] = 'text/csv'
    
    return response


@app.route('/export/pdf')
def export_pdf():
    """Export data to PDF report"""
    # Create PDF in memory
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4)
    
    # Get styles
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=24,
        spaceAfter=30,
        textColor=colors.HexColor('#4f46e5')
    )
    
    # Build PDF content
    story = []
    
    # Title
    title = Paragraph("SplitMate Expense Report", title_style)
    story.append(title)
    story.append(Spacer(1, 12))
    
    # Summary section
    expenses = Expense.query.all()
    settlements = Settlement.query.all()
    friends = Friend.query.all()
    
    total_expenses = sum(exp.amount for exp in expenses)
    total_settlements = sum(s.amount for s in settlements)
    
    summary_data = [
        ['Summary', ''],
        ['Total Friends', str(len(friends))],
        ['Total Expenses', f'₹{total_expenses:.2f}'],
        ['Total Settlements', f'₹{total_settlements:.2f}'],
        ['Report Generated', datetime.now().strftime('%Y-%m-%d %H:%M:%S')]
    ]
    
    summary_table = Table(summary_data, colWidths=[3*inch, 2*inch])
    summary_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#4f46e5')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 14),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
        ('GRID', (0, 0), (-1, -1), 1, colors.black)
    ]))
    
    story.append(summary_table)
    story.append(Spacer(1, 24))
    
    # Recent Expenses
    story.append(Paragraph("Recent Expenses", styles['Heading2']))
    story.append(Spacer(1, 12))
    
    recent_expenses = Expense.query.order_by(Expense.timestamp.desc()).limit(10).all()
    
    expense_data = [['Date', 'Description', 'Amount', 'Paid By']]
    for expense in recent_expenses:
        expense_data.append([
            expense.timestamp.strftime('%Y-%m-%d'),
            expense.description,
            f'₹{expense.amount:.2f}',
            expense.paid_by.name
        ])
    
    expense_table = Table(expense_data, colWidths=[1.5*inch, 2.5*inch, 1*inch, 1.5*inch])
    expense_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#4f46e5')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 12),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
        ('GRID', (0, 0), (-1, -1), 1, colors.black)
    ]))
    
    story.append(expense_table)
    
    # Build PDF
    doc.build(story)
    
    # Return PDF response
    buffer.seek(0)
    response = make_response(buffer.read())
    response.headers['Content-Disposition'] = f'attachment; filename=splitmate_report_{datetime.now().strftime("%Y%m%d_%H%M%S")}.pdf'
    response.headers['Content-Type'] = 'application/pdf'
    
    return response
if __name__ == '__main__':
    with app.app_context():
        # Ensure data directory exists before creating database
        data_dir = os.path.join(basedir, 'data')
        os.makedirs(data_dir, exist_ok=True)
        db.create_all()
    
    # Use host='0.0.0.0' for Docker and proper port
    port = int(os.environ.get('PORT', 5000))
    debug_mode = os.environ.get('FLASK_ENV') == 'development'
    app.run(host='0.0.0.0', port=port, debug=debug_mode)