# Investment Fund Management System

A microservices-based system for managing investment funds with user authentication, asset management, and director approvals.

## Services

- **auth_service** (Port 5000): User registration, login, account deletion
- **employee_service** (Port 5001): Asset search, buy/sell order creation
- **director_service** (Port 5002): Order approval/rejection, reporting
- **MongoDB**: Asset storage
- **Redis**: Order queue
- **PostgreSQL**: User authentication database

## Quick Start

### Prerequisites

- Docker and Docker Compose
- Python 3.12+ (for local development)
- Virtual environment (`python -m venv .venv`)

### Local Development (Python)

1. **Activate venv:**
   ```bash
   .venv\Scripts\Activate.ps1
   ```

2. **Install auth service:**
   ```bash
   pip install -r auth_service/requirements.txt
   python auth_service/app.py
   ```

3. **In another terminal, install employee service:**
   ```bash
   pip install -r employee_service/requirements.txt
   python employee_service/app.py
   ```

4. **In another terminal, install director service:**
   ```bash
   pip install -r director_service/requirements.txt
   python director_service/app.py
   ```

### Docker Compose

```bash
docker-compose up --build
```

## API Endpoints

### Authentication Service (5000)

**Register:** `POST /register`
```json
{
  "forename": "John",
  "surname": "Doe",
  "email": "john@example.com",
  "password": "password123"
}
```

**Login:** `POST /login`
```json
{
  "email": "john@example.com",
  "password": "password123"
}
```
Returns: `{ "accessToken": "..." }`

**Delete:** `POST /delete`
- Header: `Authorization: Bearer <token>`

### Employee Service (5001)

**Search Assets:** `POST /search`
```json
{
  "name": "laptop",
  "category": "Technology",
  "buying_date": "2026-01-01T00:00:00Z",
  "selling_date": "2026-12-31T23:59:59Z",
  "info_filters": [
    {
      "field": "specs.cpu",
      "operator": "$eq",
      "value": "Intel i7"
    }
  ]
}
```

**Create Buy Order:** `POST /create_buy_order`
```json
{
  "name": "Laptop",
  "categories": ["Technology", "Hardware"],
  "buying_price": 1500,
  "info": {"specs": {"cpu": "Intel i7", "ram": 16}}
}
```

**Create Sell Order:** `POST /create_sell_order`
```json
{
  "id": "507f1f77bcf86cd799439011",
  "selling_price": 2000
}
```

### Director Service (5002)

**Get Pending Orders:** `GET /pending_orders`
- Header: `Authorization: Bearer <director_token>`

**Approve/Reject Order:** `POST /decision`
- Header: `Authorization: Bearer <director_token>`
```json
{
  "uuid": "550e8400-e29b-41d4-a716-446655440000",
  "approved": true
}
```

**Get Report:** `GET /report`
- Header: `Authorization: Bearer <director_token>`

Returns: Category statistics with spent and earned amounts.

## Initial Director

Email: `onlymoney@gmail.com`
Password: `evenmoremoney`

## Development Notes

- JWT tokens expire after 1 hour
- All passwords are hashed using werkzeug
- Employee endpoints require EMPLOYEE or DIRECTOR role
- Director endpoints require DIRECTOR role only
- Order UUIDs are auto-generated and unique
- Blockchain voting is optional and not implemented in this version
