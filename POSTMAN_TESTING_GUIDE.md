
# G-HRMS Backend: Step-by-Step Postman Testing Guide

---

## Prerequisites
1. **Backend Server Running**: Make sure your Django server is running at http://127.0.0.1:8000
2. **Superadmin Account**: Use the credentials from `seed_superadmin`:
   - Email: `deulatech@gmail.com`
   - Password: `Ghrms@Sl75qcCBJzBuJ9`

---


## Part 1: Set Up Postman Environment Variables (Optional but Recommended)
Create a Postman Environment to store tokens and IDs so you don't have to copy-paste manually every time!

1. In Postman, click the **Environment** dropdown (top-right, next to "No Environment") → **Add Environment**
2. Name it "G-HRMS Local"
3. Add these variables:
   | Variable Name       | Initial Value (Leave Blank for Now) |
   |---------------------|-------------------------------------|
   | `base_url`          | `http://127.0.0.1:8000`             |
   | `csrf_token`        |                                     |
   | `access_token`      |                                     |
   | `org_id`            |                                     |
   | `employee_id`       |                                     |
   | `document_id`       |                                     |
4. Click **Save** and select "G-HRMS Local" from the environment dropdown!

---

## Part 2: Authentication Endpoints (Login, Signup, etc.)

### Step 2.1: Get CSRF Token
CSRF tokens are required for all **POST** requests to auth endpoints (signup, login, logout, refresh)!

#### Request Details
- **Method**: `GET`
- **URL**: `{{base_url}}/api/auth/csrf/`
- **Headers**: None needed!

#### In Postman:
1. Create a new request named "Get CSRF Token"
2. Set method to `GET`
3. Set URL to `http://127.0.0.1:8000/api/auth/csrf/` (or use `{{base_url}}` if you set up the env)
4. Click **Send**

#### Response
You'll get a JSON object like this:
```json
{"csrf_token": "your_csrf_token_here"}
```

#### Save to Environment (Optional)
1. In the response, right-click the `csrf_token` value → **Set environment variable**
2. Select "G-HRMS Local" and choose the `csrf_token` variable!

---

### Step 2.2: Login as Superadmin
Now use the CSRF token to log in!

#### Request Details
- **Method**: `POST`
- **URL**: `{{base_url}}/api/auth/login/`
- **Headers**:
  - `Content-Type`: `application/json`
  - `X-CSRFToken`: `{{csrf_token}}` (or paste your CSRF token if you didn't use env variables)
- **Body**: Select **raw** → **JSON**
  ```json
  {
    "email": "deulatech@gmail.com",
    "password": "Ghrms@Sl75qcCBJzBuJ9"
  }
  ```

#### In Postman:
1. New request named "Login - Superadmin"
2. Method `POST`, URL `http://127.0.0.1:8000/api/auth/login/`
3. Go to the **Headers** tab and add the two headers above
4. Go to **Body** → **raw** → select **JSON** from the dropdown and paste the JSON above
5. Click **Send**!

#### Response:
You'll get an `access_token` which you need for all protected endpoints! Also, Postman will automatically save the `ghrms_refresh` cookie!
```json
{
  "access_token": "v4.public.eyJpc3MiOiJnLWhybXM...",
  "token_type": "Bearer",
  "expires_in": 300,
  "user": {
    "id": "your-user-id",
    "username": "superadmin",
    "role": "SUPERADMIN"
  }
}
```

#### Save Access Token to Environment (Optional):
1. Right-click the `access_token` value in the response → **Set environment variable**
2. Select "G-HRMS Local" and choose `access_token`!

---

### Step 2.3: Signup a New User (Start the Process)
Signup is a 2-step process (send OTP, then verify)!

#### Request Details
- **Method**: `POST`
- **URL**: `{{base_url}}/api/auth/signup/`
- **Headers**:
  - `Content-Type`: `application/json`
  - `X-CSRFToken`: `{{csrf_token}}`
- **Body (JSON)**:
  ```json
  {
    "username": "test.user",
    "email": "test.user@example.com",
    "password": "StrongPass@123",
    "password_confirm": "StrongPass@123"
  }
  ```

#### In Postman:
1. New request named "Start Signup (Send OTP)"
2. Send it!

#### Response:
Since we're in **DEBUG** mode, the OTP will be **printed in the server's terminal window**!
```json
{
  "detail": "A verification code has been sent to your email. Enter it to complete signup.",
  "email": "test.user@example.com",
  "expires_in": 600,
  "resend_available_in": 60
}
```

---

### Step 2.4: Verify Signup with OTP
Now finish the signup process with the OTP from the server logs!

#### Request Details
- **Method**: `POST`
- **URL**: `{{base_url}}/api/auth/signup/verify/`
- **Headers**:
  - `Content-Type`: `application/json`
  - `X-CSRFToken`: `{{csrf_token}}`
- **Body (JSON)**:
  ```json
  {
    "email": "test.user@example.com",
    "otp": "your-otp-from-server-logs"
  }
  ```

#### In Postman:
1. New request named "Verify Signup OTP"
2. Send it!

#### Response:
```json
{
  "user": {
    "id": "...",
    "username": "test.user",
    "email": "test.user@example.com",
    "role": "VIEWER",
    "status": "invited"
  }
}
```

---

### Step 2.5: Refresh the Access Token
When your `access_token` expires (every 5 minutes by default), use this to get a new one!

#### Request Details
- **Method**: `POST`
- **URL**: `{{base_url}}/api/auth/refresh/`
- **Headers**:
  - `X-CSRFToken`: `{{csrf_token}}`
- **Cookies**: Postman will automatically send the `ghrms_refresh` cookie as long as you made the login request in the same collection!

#### In Postman:
1. New request named "Refresh Token"
2. Send it!

#### Response:
New `access_token`:
```json
{
  "access_token": "new-v4.public.token...",
  "token_type": "Bearer",
  "expires_in": 300
}
```

---

### Step 2.6: Logout
This invalidates the refresh token!

#### Request Details
- **Method**: `POST`
- **URL**: `{{base_url}}/api/auth/logout/`
- **Headers**:
  - `X-CSRFToken`: `{{csrf_token}}`

#### In Postman:
1. New request named "Logout"
2. Send it! You'll get a `204 No Content` response!

---

## Part 3: Administration Endpoints (Manage Users)
These endpoints require you to be logged in as **SUPERADMIN**!

### Step 3.1: List All Users
#### Request Details
- **Method**: `GET`
- **URL**: `{{base_url}}/api/auth/admin/users/`
- **Headers**:
  - `Authorization`: `Bearer {{access_token}}`

---

### Step 3.2: Create a New Admin User (HR Personnel)
#### Request Details
- **Method**: `POST`
- **URL**: `{{base_url}}/api/auth/admin/users/`
- **Headers**:
  - `Content-Type`: `application/json`
  - `Authorization`: `Bearer {{access_token}}`
- **Body (JSON)**:
  ```json
  {
    "username": "hr.personnel",
    "email": "hr.personnel@example.gov.np",
    "password": "StrongPass@123",
    "role": "HR_PERSONNEL"
  }
  ```
- **Possible role values**: `SUPERADMIN`, `HR_MANAGER`, `HR_PERSONNEL`, `VIEWER`

---

### Step 3.3: Update a User (Partial Update)
#### Request Details
- **Method**: `PATCH`
- **URL**: `{{base_url}}/api/auth/admin/users/{user_id}/` (replace `{user_id}` with the user's ID from listing users!)
- **Headers**:
  - `Content-Type`: `application/json`
  - `Authorization`: `Bearer {{access_token}}`
- **Body (JSON)**:
  ```json
  {
    "role": "HR_MANAGER",
    "first_name": "John",
    "last_name": "Doe"
  }
  ```

---

### Step 3.4: Activate/Deactivate a User (Change Status)
You can activate users who signed up (they start in "invited" status)!
#### Request Details
- **Method**: `PATCH`
- **URL**: `{{base_url}}/api/auth/admin/users/{user_id}/status/`
- **Headers**:
  - `Content-Type`: `application/json`
  - `Authorization`: `Bearer {{access_token}}`
- **Body (JSON)**:
  ```json
  {"status": "active"}
  ```
  - **Possible status values**: `active`, `suspended`

---

### Step 3.5: Delete (Soft Delete/Deactivate) a User
#### Request Details
- **Method**: `DELETE`
- **URL**: `{{base_url}}/api/auth/admin/users/{user_id}/`
- **Headers**:
  - `Authorization`: `Bearer {{access_token}}`

---

## Part 4: Organization & Service Catalog Endpoints
These endpoints require authentication (Bearer token)!

First, we need to create some foundational data for employees (we need an organization, service, category, subcategory, level, and position first)!

---

### Step 4.1: Create a Service
#### Request Details
- **Method**: `POST`
- **URL**: `{{base_url}}/api/services/`
- **Headers**:
  - `Content-Type`: `application/json`
  - `Authorization`: `Bearer {{access_token}}`
- **Body (JSON)**:
  ```json
  {"name": "Administration Service"}
  ```

---

### Step 4.2: Create a Category (Belongs to a Service)
#### Request Details
- **Method**: `POST`
- **URL**: `{{base_url}}/api/categories/`
- **Headers**:
  - `Content-Type`: `application/json`
  - `Authorization`: `Bearer {{access_token}}`
- **Body (JSON)**:
  ```json
  {
    "name": "General Administration",
    "service": 1  /* Use the ID of the service you just created! */
  }
  ```

---

### Step 4.3: Create a Subcategory
#### Request Details
- **Method**: `POST`
- **URL**: `{{base_url}}/api/subcategories/`
- **Headers**:
  - `Content-Type`: `application/json`
  - `Authorization`: `Bearer {{access_token}}`
- **Body (JSON)**:
  ```json
  {
    "name": "Personnel Administration",
    "category": 1 /* Use ID from step 4.2! */
  }
  ```

---

### Step 4.4: Create a Level
#### Request Details
- **Method**: `POST`
- **URL**: `{{base_url}}/api/levels/`
- **Headers**:
  - `Content-Type`: `application/json`
  - `Authorization`: `Bearer {{access_token}}`
- **Body (JSON)**:
  ```json
  {
    "name": "Level 7",
    "gazetted_type": "NON_GAZETTED"
  }
  ```
  - **Possible gazetted types**: `GAZETTED`, `NON_GAZETTED`

---

### Step 4.5: Create a Position
#### Request Details
- **Method**: `POST`
- **URL**: `{{base_url}}/api/positions/`
- **Headers**:
  - `Content-Type`: `application/json`
  - `Authorization`: `Bearer {{access_token}}`
- **Body (JSON)**:
  ```json
  {
    "title": "Personnel Officer",
    "service": 1,
    "category": 1,
    "subcategory": 1,
    "level": 1
  }
  ```
  (Use the IDs from steps 4.1-4.4!)

---

### Step 4.6: Create an Organization
#### Request Details
- **Method**: `POST`
- **URL**: `{{base_url}}/api/organizations/`
- **Headers**:
  - `Content-Type`: `application/json`
  - `Authorization`: `Bearer {{access_token}}`
- **Body (JSON)**:
  ```json
  {
    "name": "Ministry of Public Administration",
    "code": "MPA-001",
    "org_type": "ministry",
    "province": "03",
    "address": "Hetauda, Makwanpur",
    "established_date_ad": "2024-01-01",
    "established_date_bs": "2080-09-17",
    "is_active": true,
    "parent_org": null
  }
  ```
- **Possible org_type values**: `ministry`, `department`, `office`, `branch`, `division`
- **Possible province values**: 01 (Koshi) to 07 (Sudurpashchim), plus 08 for Federal!

#### Save Org ID to Environment:
Right-click the `id` in the response and set it to `org_id` in your env variables!

---

### Step 4.7: List All Organizations
#### Request Details
- **Method**: `GET`
- **URL**: `{{base_url}}/api/organizations/`
- **Headers**:
  - `Authorization`: `Bearer {{access_token}}`
- **Optional Query Params**:
  - `org_type`: Filter by type (e.g., `?org_type=ministry`)
  - `province`: Filter by province (e.g., `?province=03`)
  - `is_active`: Filter by active status (e.g., `?is_active=true`)
  - `search`: Search by name/code/address (e.g., `?search=Public`)

---

### Step 4.8: Get, Update, or Delete a Single Organization
All of these use the organization ID in the URL!
- **GET**: `{{base_url}}/api/organizations/{org_id}/` (retrieve details)
- **PATCH**: `{{base_url}}/api/organizations/{org_id}/` (partial update)
- **DELETE**: `{{base_url}}/api/organizations/{org_id}/` (delete)

---

## Part 5: Employees & Office Transfers
Now that we have an organization and position, we can create an employee!

---

### Step 5.1: Create an Employee
#### Request Details
- **Method**: `POST`
- **URL**: `{{base_url}}/api/employees/`
- **Headers**:
  - `Content-Type`: `application/json`
  - `Authorization`: `Bearer {{access_token}}`
- **Body (JSON)**:
  ```json
  {
    "ka_sa_num": "EMP-2024-0001",
    "first_name": "Sita",
    "middle_name": "Kumari",
    "last_name": "Shrestha",
    "father_name": "Ram Shrestha",
    "grandfather_name": "Hari Shrestha",
    "spouse_name": "Bikash Shrestha",
    "beneficiary_name": "Aarav Shrestha",
    "permanent_address": "Hetauda, Makwanpur",
    "citizenship_number": "31-01-75-12345",
    "gender": "Female",
    "gender_other": null,
    "dob_bs": "2050-01-01",
    "dob_ad": "1993-04-14",
    "email": "sita.shrestha@example.gov.np",
    "phone_number": "+9779812345678",
    "employment_type": "permanent",
    "status": "IN_SERVICE",
    "jobstartdate_bs": "2080-01-01",
    "jobstartdate_ad": "2023-04-14",
    "current_position_date_bs": "2080-01-01",
    "current_position_date_ad": "2023-04-14",
    "working_organization": 1, /* ID from step 4.6! */
    "position": 1, /* ID from step 4.5! */
    "level": 1, /* ID from step 4.4! */
    "supervisor": null,
    "remarks": "Initial appointment"
  }
  ```
Possible gender values: "Male", "Female", "Other"
Possible employment type: "permanent", "contract", "temporary"
Possible status: "IN_SERVICE", "ON_LEAVE", "TRANSFERRED", "RETIRED", "TERMINATED"

#### Save Employee ID:
Right-click `id` in response and set to `employee_id` in env!

---

### Step 5.2: List All Employees
#### Request Details
- **Method**: `GET`
- **URL**: `{{base_url}}/api/employees/`
- **Headers**:
  - `Authorization`: `Bearer {{access_token}}`
- **Optional Query Params**:
  - `search`: Search by name, email, citizenship number, ka_sa_num
  - Filter by working_organization, status, etc.

---

### Step 5.3: Get, Update, or Delete an Employee
Same pattern as organizations!

---

### Step 5.4: Create an Office Transfer
#### Request Details
- **Method**: `POST`
- **URL**: `{{base_url}}/api/office-transfers/`
- **Headers**:
  - `Content-Type`: `application/json`
  - `Authorization`: `Bearer {{access_token}}`
- **Body (JSON)**:
  ```json
  {
    "employee": 1, /* Employee ID from step 5.1! */
    "to_organization": 1,
    "from_position": 1,
    "to_position": 1,
    "from_level": 1,
    "to_level": 1,
    "decision_date_ad": "2024-07-15",
    "decision_date_bs": "2081-04-01",
    "to_date_ad": "2024-08-01",
    "to_date_bs": "2081-04-17",
    "status": "PENDING",
    "remarks": "Transfer to new office"
  }
  ```

---

## Part 6: Documents Endpoints
Now let's upload and manage employee documents!

---

### Step 6.1: Submit a Document (with File Upload)
We use `form-data` here because we're uploading a file!

#### Request Details
- **Method**: `POST`
- **URL**: `{{base_url}}/api/documents/`
- **Headers**:
  - `Authorization`: `Bearer {{access_token}}` (**NO NEED FOR Content-Type header here!** Postman will set it automatically for form-data!)
- **Body**: Select **form-data**!
  Add these keys:
  | Key               | Value                                                                 |
  |-------------------|-----------------------------------------------------------------------|
  | `employee`        | `{{employee_id}}` (or paste your employee's ID)                       |
  | `category`        | `CITIZENSHIP` (or `PASSPORT`, `CV`, `EDUCATION`, `TRAINING`, `OTHER`) |
  | `title`           | `Citizenship Certificate of Sita Shrestha`                           |
  | `file`            | Click **Select Files** and choose a file from your computer!          |
  | `upload_source`   | `HR` (or `EMPLOYEE`)                                                 |

#### In Postman:
1. Go to **Body** → select **form-data**
2. For the `file` key: change the dropdown on the right from **Text** to **File**, then click **Select Files**!
3. Send it!

---

### Step 6.2: List All Documents
#### Request Details
- **Method**: `GET`
- **URL**: `{{base_url}}/api/documents/`
- **Headers**:
  - `Authorization`: `Bearer {{access_token}}`

---

### Step 6.3: Upload a New Version of an Existing Document
#### Request Details
- **Method**: `POST`
- **URL**: `{{base_url}}/api/documents/{document_id}/versions/`
- **Headers**:
  - `Authorization`: `Bearer {{access_token}}`
- **Body**: `form-data`, with a `file` key and optionally `upload_source`

---

### Step 6.4: Verify a Document Version
#### Request Details
- **Method**: `POST`
- **URL**: `{{base_url}}/api/document-versions/{version_id}/verify/`
- **Headers**:
  - `Content-Type`: `application/json`
  - `Authorization`: `Bearer {{access_token}}`
- **Body (JSON)**:
  ```json
  {
    "decision": "APPROVED", /* or "REJECTED" */
    "remarks": "Looks good!",
    "checklist": {
      "id_verified": true,
      "signature_verified": true
    }
  }
  ```

---

## Part 7: Swagger UI (Bonus: Interactive Documentation!)
If you don't want to use Postman, you can use the built-in Swagger UI at **http://127.0.0.1:8000/api/docs/**! Just log in via Postman first, get your `access_token`, and click **Authorize** in Swagger!

---

## And That's It!
You've tested all major endpoints in Postman! If you want to organize all your requests into a Postman Collection, just drag them into a folder in Postman!
