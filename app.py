import os
import sqlite3
from datetime import date
from flask import Flask, render_template, request, redirect, url_for, flash, abort

app = Flask(__name__)
app.secret_key = 'replace-with-secure-key'

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, 'SmartBuildingMaintenance.db')

ENTITY_CONFIG = {
    'building': {
        'table': 'Building',
        'pk': 'building_id',
        'label': 'Building',
        'fields': ['name', 'floors', 'manager_name', 'manager_phone'],
        'headers': ['ID', 'Name', 'Floors', 'Manager', 'Phone'],
        'select_fields': ['building_id', 'name', 'floors', 'manager_name', 'manager_phone'],
    },
    'room': {
        'table': 'Room',
        'pk': 'room_id',
        'label': 'Room',
        'fields': ['building_id', 'room_type', 'capacity'],
        'headers': ['ID', 'Building', 'Type', 'Capacity'],
        'select_sql': (
            'SELECT r.room_id, b.name AS building, r.room_type, r.capacity '
            'FROM Room r LEFT JOIN Building b ON r.building_id = b.building_id '
            'ORDER BY r.room_id DESC'
        ),
    },
    'equipment': {
        'table': 'Equipment',
        'pk': 'equipment_id',
        'label': 'Equipment',
        'fields': ['room_id', 'name', 'serial_number', 'category', 'purchase_date', 'status'],
        'headers': ['ID', 'Name', 'Serial', 'Category', 'Purchased', 'Status', 'Room', 'Building'],
        'select_sql': (
            'SELECT e.equipment_id, e.name, e.serial_number, e.category, e.purchase_date, e.status, '
            'rm.room_type AS room, b.name AS building '
            'FROM Equipment e '
            'LEFT JOIN Room rm ON e.room_id = rm.room_id '
            'LEFT JOIN Building b ON rm.building_id = b.building_id '
            'ORDER BY e.equipment_id DESC'
        ),
    },
    'technician': {
        'table': 'Technician',
        'pk': 'technician_id',
        'label': 'Technician',
        'fields': ['first_name', 'last_name', 'phone', 'email', 'specialty'],
        'headers': ['ID', 'First Name', 'Last Name', 'Phone', 'Email', 'Specialty'],
        'select_fields': ['technician_id', 'first_name', 'last_name', 'phone', 'email', 'specialty'],
    },
    'request': {
        'table': 'RepairRequest',
        'pk': 'request_id',
        'label': 'Repair Request',
        'fields': ['equipment_id', 'room_id', 'building_id', 'technician_id', 'request_date', 'reported_by', 'problem_description', 'priority', 'status', 'resolution', 'completion_date'],
        'headers': ['ID', 'Request Date', 'Equipment', 'Technician', 'Priority', 'Status', 'Building', 'Room'],
        'select_sql': (
            'SELECT r.request_id, r.request_date, e.name AS equipment, '
            'COALESCE(t.first_name || " " || t.last_name, "Unassigned") AS technician, '
            'r.priority, r.status, b.name AS building, rm.room_type AS room '
            'FROM RepairRequest r '
            'LEFT JOIN Equipment e ON r.equipment_id = e.equipment_id '
            'LEFT JOIN Technician t ON r.technician_id = t.technician_id '
            'LEFT JOIN Building b ON r.building_id = b.building_id '
            'LEFT JOIN Room rm ON r.room_id = rm.room_id '
            'ORDER BY r.request_date DESC'
        ),
    },
}

STATUS_OPTIONS = ['Open', 'In Progress', 'Pending', 'Completed']
PRIORITY_OPTIONS = ['Low', 'Normal', 'High', 'Critical']
EQUIPMENT_STATUS_OPTIONS = ['Active', 'Maintenance', 'Faulty', 'Retired']


def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def validate_entity(entity):
    config = ENTITY_CONFIG.get(entity)
    if not config:
        abort(404)
    return config


def get_all_rows(entity):
    config = validate_entity(entity)
    conn = get_db_connection()
    if 'select_sql' in config:
        rows = conn.execute(config['select_sql']).fetchall()
    else:
        columns = ', '.join(config['select_fields'])
        rows = conn.execute(f'SELECT {columns} FROM {config["table"]} ORDER BY {config["pk"]} DESC').fetchall()
    conn.close()
    return rows


def get_row(entity, pk_value):
    config = validate_entity(entity)
    conn = get_db_connection()
    row = conn.execute(f'SELECT * FROM {config["table"]} WHERE {config["pk"]} = ?', (pk_value,)).fetchone()
    conn.close()
    if not row:
        abort(404)
    return row


def get_select_options():
    conn = get_db_connection()
    buildings = conn.execute('SELECT building_id, name FROM Building ORDER BY name').fetchall()
    rooms = conn.execute('SELECT room_id, room_type, building_id FROM Room ORDER BY room_id').fetchall()
    equipments = conn.execute('SELECT equipment_id, name, room_id FROM Equipment ORDER BY name').fetchall()
    technicians = conn.execute('SELECT technician_id, first_name, last_name FROM Technician ORDER BY first_name').fetchall()
    conn.close()
    return {
        'buildings': buildings,
        'rooms': rooms,
        'equipments': equipments,
        'technicians': technicians,
    }


def save_entity(entity, data, pk_value=None):
    config = validate_entity(entity)
    conn = get_db_connection()
    if pk_value is None:
        fields = [f for f in config['fields'] if f in data]
        placeholders = ', '.join('?' for _ in fields)
        columns = ', '.join(fields)
        values = [data[f] for f in fields]
        conn.execute(f'INSERT INTO {config["table"]} ({columns}) VALUES ({placeholders})', values)
        conn.commit()
        conn.close()
        return

    fields = [f for f in config['fields'] if f in data]
    assignments = ', '.join(f'{f} = ?' for f in fields)
    values = [data[f] for f in fields] + [pk_value]
    conn.execute(f'UPDATE {config["table"]} SET {assignments} WHERE {config["pk"]} = ?', values)
    conn.commit()
    conn.close()


def delete_entity(entity, pk_value):
    config = validate_entity(entity)
    conn = get_db_connection()
    conn.execute(f'DELETE FROM {config["table"]} WHERE {config["pk"]} = ?', (pk_value,))
    conn.commit()
    conn.close()


def get_dashboard_data():
    conn = get_db_connection()
    pending_count = conn.execute(
        "SELECT COUNT(*) FROM RepairRequest WHERE status NOT IN ('Completed', 'completed') OR status IS NULL"
    ).fetchone()[0]
    totals = {
        'buildings': conn.execute('SELECT COUNT(*) FROM Building').fetchone()[0],
        'rooms': conn.execute('SELECT COUNT(*) FROM Room').fetchone()[0],
        'equipment': conn.execute('SELECT COUNT(*) FROM Equipment').fetchone()[0],
        'technicians': conn.execute('SELECT COUNT(*) FROM Technician').fetchone()[0],
        'requests': conn.execute('SELECT COUNT(*) FROM RepairRequest').fetchone()[0],
    }
    latest_requests = conn.execute(
        'SELECT r.request_id, r.request_date, e.name AS equipment, COALESCE(t.first_name || " " || t.last_name, "Unassigned") AS technician, r.status '
        'FROM RepairRequest r '
        'LEFT JOIN Equipment e ON r.equipment_id = e.equipment_id '
        'LEFT JOIN Technician t ON r.technician_id = t.technician_id '
        'ORDER BY r.request_date DESC LIMIT 5'
    ).fetchall()
    conn.close()
    return pending_count, totals, latest_requests


@app.route('/')
def home():
    pending_count, totals, latest_requests = get_dashboard_data()
    return render_template(
        'index.html',
        page='dashboard',
        pending_count=pending_count,
        totals=totals,
        latest_requests=latest_requests,
        nav_items=[
            ('building', 'Buildings'),
            ('room', 'Rooms'),
            ('equipment', 'Equipment'),
            ('technician', 'Technicians'),
            ('request', 'Repair Requests'),
        ],
    )


@app.route('/manage/<entity>')
def manage_list(entity):
    config = validate_entity(entity)
    rows = get_all_rows(entity)
    return render_template(
        'index.html',
        page='list',
        entity=entity,
        config=config,
        rows=rows,
        nav_items=[
            ('building', 'Buildings'),
            ('room', 'Rooms'),
            ('equipment', 'Equipment'),
            ('technician', 'Technicians'),
            ('request', 'Repair Requests'),
        ],
    )


@app.route('/manage/<entity>/create', methods=['GET', 'POST'])
def manage_create(entity):
    config = validate_entity(entity)
    select_options = get_select_options()
    if request.method == 'POST':
        form_data = {field: request.form.get(field) or None for field in config['fields']}
        if entity == 'request':
            form_data['request_date'] = form_data['request_date'] or date.today().isoformat()
        save_entity(entity, form_data)
        flash(f'{config["label"]} created successfully.', 'success')
        return redirect(url_for('manage_list', entity=entity))
    row = {field: '' for field in config['fields']}
    row[config['pk']] = ''
    return render_template(
        'index.html',
        page='form',
        entity=entity,
        config=config,
        row=row,
        select_options=select_options,
        status_options=STATUS_OPTIONS,
        priority_options=PRIORITY_OPTIONS,
        equipment_status_options=EQUIPMENT_STATUS_OPTIONS,
        nav_items=[
            ('building', 'Buildings'),
            ('room', 'Rooms'),
            ('equipment', 'Equipment'),
            ('technician', 'Technicians'),
            ('request', 'Repair Requests'),
        ],
    )


@app.route('/manage/<entity>/<int:pk>/edit', methods=['GET', 'POST'])
def manage_edit(entity, pk):
    config = validate_entity(entity)
    row = get_row(entity, pk)
    select_options = get_select_options()
    if request.method == 'POST':
        form_data = {field: request.form.get(field) or None for field in config['fields']}
        if entity == 'request':
            form_data['request_date'] = form_data['request_date'] or date.today().isoformat()
        save_entity(entity, form_data, pk_value=pk)
        flash(f'{config["label"]} updated successfully.', 'success')
        return redirect(url_for('manage_list', entity=entity))
    return render_template(
        'index.html',
        page='form',
        entity=entity,
        config=config,
        row=row,
        select_options=select_options,
        status_options=STATUS_OPTIONS,
        priority_options=PRIORITY_OPTIONS,
        equipment_status_options=EQUIPMENT_STATUS_OPTIONS,
        nav_items=[
            ('building', 'Buildings'),
            ('room', 'Rooms'),
            ('equipment', 'Equipment'),
            ('technician', 'Technicians'),
            ('request', 'Repair Requests'),
        ],
    )


@app.route('/manage/<entity>/<int:pk>/delete')
def manage_delete(entity, pk):
    config = validate_entity(entity)
    delete_entity(entity, pk)
    flash(f'{config["label"]} deleted successfully.', 'warning')
    return redirect(url_for('manage_list', entity=entity))


if __name__ == '__main__':
    app.run(debug=True, port=5000)
