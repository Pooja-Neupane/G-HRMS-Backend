# BagamatiERIS

Bagamati Province Employee Record Information System (BagamatiERIS) is a
Django REST Framework backend for managing government personnel,
organizational structures, and employee transfer history.

The application uses PostgreSQL and includes account, role-based access
control (RBAC), audit history, and token-rotation data models.

## Features

- Employee profiles, employment status, and personnel details
- Office transfer history with Gregorian (AD) and Bikram Sambat (BS) dates
- Hierarchical organizations, services, categories, positions, and levels
- Custom Django user model with application roles and account status
- Granular role permissions and module-access rules
- Historical record tracking and soft deletion
- OpenAPI schema, Swagger UI, and ReDoc documentation

## Technology Stack

- Python 3.10+
- Django 5.2
- Django REST Framework
- PostgreSQL with Psycopg 3
- drf-spectacular
- django-filter
- django-simple-history

## Project Structure

```text
backend/
|-- account/          # Users, roles, permissions, and authentication events
|-- core/             # Django settings, shared models, middleware, and URLs
|-- employees/        # Employee profiles and office transfer records
|-- organizations/    # Organization hierarchy and civil-service structures
|-- template/         # DRF browsable API templates
|-- manage.py
|-- requirements.txt
`-- .env              # Local database credentials (not committed)
```

## Local Setup

### 1. Prerequisites

Install the following tools:

- Python 3.10 or newer
- PostgreSQL server
- PostgreSQL command-line client (`psql`)

Confirm they are available:

```bash
python3 --version
psql --version
```

On Ubuntu, PostgreSQL can be installed and started with:

```bash
sudo apt update
sudo apt install postgresql postgresql-contrib libpq-dev
sudo systemctl enable --now postgresql
```

### 2. Create the PostgreSQL Database

Open the PostgreSQL shell as its administrative user:

```bash
sudo -u postgres psql
```

Create a project user and database at the `postgres=#` prompt:

```sql
CREATE USER bagamati_eris_user WITH PASSWORD 'replace-with-a-strong-password';
CREATE DATABASE bagamati_eris OWNER bagamati_eris_user;
\q
```

The database owner has the schema permissions Django needs to run migrations.

### 3. Create the Python Environment

From the project root:

```bash
python3 -m venv venv
source venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### 4. Configure Environment Variables

Create `.env` in the project root:

```ini
DB_NAME=bagamati_eris
DB_USER=bagamati_eris_user
DB_PASSWORD=replace-with-a-strong-password
DB_HOST=127.0.0.1
DB_PORT=5432
```

The `.env` file is ignored by Git and must not be committed.

### 5. Initialize Django

```bash
python manage.py check
python manage.py migrate
python manage.py createsuperuser
```

### 6. Run the Development Server

```bash
python manage.py runserver
```

The local API is available at `http://127.0.0.1:8000/`.

## API Routes

| Route | Description |
| --- | --- |
| `/admin/` | Django administration |
| `/api/employees/` | Employee records |
| `/api/office-transfers/` | Office transfer records |
| `/api/organizations/` | Organizations |
| `/api/services/` | Civil-service classifications |
| `/api/categories/` | Service categories |
| `/api/subcategories/` | Service subcategories |
| `/api/positions/` | Government positions |
| `/api/schema/` | OpenAPI schema |
| `/api/docs/` | Swagger UI |
| `/api/redoc/` | ReDoc documentation |

Router endpoints support the HTTP methods implemented by their corresponding
Django REST Framework viewsets.

## Working with `psql`

Connect to the application database:

```bash
psql -h 127.0.0.1 -U bagamati_eris_user -d bagamati_eris
```

Useful commands inside `psql`:

```text
\l                  List databases
\dt                 List tables
\d account_user     Describe the custom user table
\conninfo           Show the current connection
\q                  Exit psql
```

## Tests

Run the Django test suite with:

```bash
python manage.py test
```

## Security Notes

- Use strong PostgreSQL and Django administrator passwords.
- Keep `.env`, private keys, uploaded media, and local logs out of Git.
- Do not run Django with development settings in production.
- Restrict database and application network access before deployment.
