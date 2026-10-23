# Authentication, email verification, and password recovery

Use synthetic or de-identified records only. Do not deploy with real student data
until privacy, consent, school approval, access controls, and security safeguards
have been reviewed. This change does not implement a counselor dashboard.

## Install and migrate

Use Python 3.11+ and Node compatible with the frontend's Vite version:

```bash
python3 -m venv env
source env/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env  # only for a new setup; preserve existing local secrets
python -m alembic upgrade head
python -m alembic current
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Back up an existing SQLite database before migrating (stop application writes or
use SQLite's backup API). `0001_legacy` adopts existing legacy tables without
rewriting them and creates missing tables for a fresh install. `0002_auth` adds
`users`, `auth_sessions`, and `auth_attempts`. `0003_email_verification` adds
`users.email_verified_at` and `email_challenges`, and revokes existing signed-in
sessions. Existing accounts are preserved but are **not** silently verified: their
owners must use **Forgot password** to prove inbox ownership and choose a fresh
password before signing in. No student records are reassigned. Do not stamp a
database blindly.
Startup requires the current migration revision and then seeds questionnaire
definitions as before. The baseline downgrade is deliberately disabled; restore a
reviewed backup if necessary. Downgrading the auth revision removes accounts and
sessions, so it is not a data-preserving rollback.

Existing student, answer, and conversation rows are not claimed by registration.
`users.student_id` is a unique nullable FK, with a one-to-one ORM relationship;
user IDs and student IDs are independent. Successful email-code verification creates
a fresh student and user transactionally. Requesting registration creates only a
short-lived pending challenge, with an Argon2 password hash; no student or authenticated
session exists until inbox ownership is proved. Counselors have no student link. Existing unclaimed records
remain stored but are inaccessible through authenticated student APIs.

## Environment and browser login

Keep `.env` private. Never put API keys in `VITE_*` variables. Configure:

- `DATABASE_URL`: defaults to `sqlite:///./student.db`.
- `ENVIRONMENT=development` locally; `production` requires secure cookies and HTTPS origins.
- `CORS_ORIGINS`: JSON array of explicit frontend origins, without trailing slashes.
  Defaults include `http://127.0.0.1:5173` and `http://localhost:5173`. Wildcards are rejected.
- `COOKIE_SECURE=false` for local HTTP; **true for production**. Production-style
  cookies use the `__Host-` prefix, Path=/, no Domain, HttpOnly, and Secure.
- `COOKIE_SAMESITE=lax` by default. Prefer a same-site frontend/API deployment.
  A truly cross-site deployment requires `none` and Secure, and must account for
  browsers that block third-party cookies. SameSite is not the CSRF mechanism.
- `SESSION_HOURS=8`: absolute server-side session lifetime, configurable 1–24 hours.
  Anonymous CSRF bootstrap sessions expire in 30 minutes.
- `AUTH_RATE_LIMIT=10`: attempts per normalized email per 15 minutes, shared through
  the database. Registration, login, code checks, resends, and password recovery share
  this budget. `AUTH_IP_RATE_LIMIT=300` is the separate per-IP limit, so a school
  sharing one public IP is not restricted to ten attempts for the whole classroom.
  Tune the IP budget alongside the deployment’s trusted proxy and edge limiter.
- `AUTH_DEV_COMMANDS=false`: enable explicitly only for local synthetic fixtures.

```bash
cd frontend
npm install
# frontend/.env.local, if needed: VITE_API_BASE_URL=http://127.0.0.1:8000
npm run dev
```

Configure SMTP as described below, then visit `http://127.0.0.1:5173`.
The welcome dashboard retains its sidebar, path illustration, and journey cards;
account creation appears inside the student-space panel. Create a test account
using an inbox you control and synthetic assessment details. Enter the 8-digit
email code to complete registration. Complete some answers, refresh, and confirm
they persist. Sign out and confirm student navigation disappears. Sign
back in to resume. Use the same hostname for both servers: mixing localhost and
127.0.0.1 can prevent SameSite cookies from being sent. The frontend uses view
state rather than a URL router; the whole student workspace is gated by `/auth/me`.
Counselors see only a restricted placeholder and sign-out.

To test recovery: sign out, select **Returning student**, choose **Forgot password?**,
and enter the account email. Enter the code from that reset request, choose a fresh
12–128 character password, and confirm it. The app returns to sign-in; the old
password and every previous signed-in session must stop working. Codes can be used
only once and expire after 10 minutes. The resend button becomes available after
60 seconds; resending replaces the code without resetting the five-guess budget.
Use the code for the request currently open in your browser. If you close the page,
start a new request. After five failed guesses, start a new request instead of
resending. Existing pre-verification accounts must complete this recovery flow.

## Configure real email delivery

The backend supports authenticated SMTP over STARTTLS or implicit TLS. There is no
console sender, displayed-code bypass, or frontend-only verification mode. Missing
SMTP configuration returns HTTP 503 for code requests and creates no account.

In the private backend `.env` file, configure the connection supplied by your school
or transactional email provider:

```dotenv
SMTP_HOST=smtp.your-provider.example
SMTP_PORT=587
SMTP_SECURITY=starttls
SMTP_FROM=pathbridge@your-approved-domain.example
SMTP_USERNAME=your-smtp-username
SMTP_PASSWORD=your-private-smtp-password
SMTP_TIMEOUT_SECONDS=10
AUTH_CODE_SECRET=replace-with-a-long-random-secret
```

Generate `AUTH_CODE_SECRET` once with
`python -c "import secrets; print(secrets.token_urlsafe(48))"` and store it privately.
It must contain at least 32 characters and must be the same across backend workers.
Rotating it invalidates outstanding codes. For implicit TLS use port 465 and
`SMTP_SECURITY=tls`. Plaintext SMTP is rejected; server certificates are verified.
If your provider uses OAuth-only mail access, it needs a compatible mail adapter;
a normal account password will not work. Use a provider-approved service credential
or app password where available. Never paste credentials into chat or put these
settings in `VITE_*` variables. Restart the backend after updating settings.

Use a verified sender/domain and configure the provider's required DNS records.
Confirm school inboxes accept the messages and that school policy permits delivery.
A successful API response means the request was accepted, not that delivery was
confirmed. Sends run in a background task after the response; delivery failures
produce a generic server log message without recipients, codes, or SMTP credentials.
There is no durable retry queue yet: monitor delivery and use resend after fixing
a mail outage. Real delivery must be smoke-tested with the configured provider;
automated tests use an in-memory mailer and never contact real inboxes.

## API contract and security

`GET /auth/csrf` establishes an anonymous session when needed and returns a CSRF
token. The email flow uses opaque, random challenge IDs alongside 8-digit codes:

| Endpoint | Request | Result |
| --- | --- | --- |
| `POST /auth/register` | email, password, optional display_name | HTTP 202, generic message and challenge_id; no account/session yet |
| `POST /auth/verify-email` | challenge_id, code | HTTP 201, `{user, csrf_token}` and rotated session cookie |
| `POST /auth/resend-verification` | email, challenge_id | Generic HTTP 202; resend subject to cooldown and attempt budget |
| `POST /auth/login` | email, password | Verified active account only; `{user, csrf_token}` and rotated session cookie |
| `POST /auth/forgot-password` | email | Generic HTTP 202 and challenge_id, whether an active account exists or not |
| `POST /auth/resend-reset` | email, challenge_id | Generic HTTP 202; resend subject to cooldown and attempt budget |
| `POST /auth/reset-password` | challenge_id, code, new_password | Changes password, verifies legacy email ownership, revokes all signed-in sessions; requires login afterward |
| `GET /auth/me` | Session cookie | Public user fields, including separate student_id and email_verified |
| `POST /auth/logout` | Session cookie and CSRF | Revokes session and clears cookie |

Every state-changing request requires an exact trusted `Origin` and the
`X-CSRF-Token` returned by `/auth/csrf` or successful authentication. This includes
registration and login. Cookies are sent with `credentials: include`; CORS allows
credentials only for configured origins. CLI clients must also supply Origin and
CSRF headers. Fetch a new CSRF token after an expired session; requests are not
automatically replayed. CSRF tokens stay in memory; no credentials or tokens are
stored in localStorage/sessionStorage.

Session identifiers use 256 bits of randomness; only SHA-256 hashes are persisted.
CSRF tokens are bound to the session and checked with a constant-time comparison.
Passwords use Argon2id via argon2-cffi, with rehashing on successful login. Unknown,
inactive, and incorrect-password login failures share a generic message and a
password verification path. Registration and recovery requests return the same generic accepted response for
eligible and ineligible addresses, with random-looking challenge IDs. Registration
never replaces an existing account or its password. Code checks use a maximum of
five guesses per challenge, a ten-minute expiration, and atomic single-use
consumption. Stored code verifiers use HMAC-SHA256 with the private server key,
challenge ID, and purpose, so a database-only leak does not permit offline guessing
of short codes. A registration code cannot reset a password. Successful verification
or reset invalidates all outstanding challenges for that email. Password resets
revoke existing sessions and send a password-change notification; they do not log
in the user. Login uses a conditional database update to serialize against password
resets. These controls follow the [OWASP recovery guidance](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html). Validation errors omit raw inputs. Application
code never logs credentials, sessions, assessment responses, or profiles. Configure
reverse proxy/APM logging to avoid request bodies, Cookie and CSRF headers.

Student endpoint paths and response shapes remain compatible, but anonymous
access is intentionally removed. All `/students/{student_id}` APIs enforce the
linked student's ownership; another student's ID returns 404, and counselors get
403. Questionnaire definitions remain public because they contain no student
responses. `POST /students` now requires a student account without a link and
returns 409 for normal registered accounts, preventing duplicate/orphan profiles.
Use `/auth/register` for onboarding. The old student ID selector is removed.
Future recommendations and counselor APIs must use the reusable dependencies in
`app/api/auth.py`; counselor access additionally needs an explicit assignment
model before any student data can be exposed.

## Restricted local account commands

Commands prompt twice for a password, never accept it as a command-line argument,
never reassign existing accounts, and require both development mode and an explicit
synthetic-data acknowledgment. Start from a migrated database:

```bash
ENVIRONMENT=development AUTH_DEV_COMMANDS=true python -m scripts.auth_admin --synthetic-data-only create-counselor --email counselor@example.org
ENVIRONMENT=development AUTH_DEV_COMMANDS=true python -m scripts.auth_admin --synthetic-data-only link-synthetic-student --email legacy@example.org --student-id 12
```

The second command creates a new student account linked to one explicitly selected,
unclaimed synthetic legacy record. It does not match by name or guess ownership.
There is no public counselor-registration endpoint or public legacy-link endpoint.
These explicitly synthetic local commands mark their test accounts verified; they
are unavailable in production. They are not a real student onboarding process.

## Tests and pilot limitations

```bash
python -m pytest -q
cd frontend
npm test
npm run build
npm run lint
```

`tests/test_auth.py` exercises real sessions and ownership without authorization
overrides. `tests/test_email_auth.py` covers inbox verification and recovery, and
`tests/test_mail.py` tests encrypted SMTP behavior without sending actual email. Legacy contract tests explicitly override auth dependencies to isolate
existing assessment/chat behavior. LLM and embedding tests use mocks and require
no paid OpenAI calls. Migration tests verify legacy row preservation.

Before any real student pilot, review school agreements, consent, age/retention and
deletion policies, provider data flows, incident handling, backups, HTTPS/proxy
configuration, mail delivery, and independent security testing. Removing the
preview text does not establish approval to process real student information.
MFA for staff, audit trails, counselor assignments, and stronger abuse defenses are
not implemented. Rate limits are DB-backed but concurrent
requests can slightly exceed the threshold; an atomic shared limiter at the edge
is needed for a public deployment. Client IP comes from the socket, not untrusted
forwarded headers; configure a trusted proxy/edge limiter deliberately. Bootstrap
requests need edge rate limiting too. Expired/revoked sessions, old rate records,
and expired/consumed email challenges are not automatically deleted; schedule a
reviewed retention cleanup. Pending registration challenges contain email, an
optional display name, and a password hash until consumed or cleaned up. SHA-256
rate-limit keys are pseudonymous, not anonymous. SQLite is suitable for local
validation, not yet validated for school-scale concurrent use. A session is a
bearer credential; XSS can still act as the user, so review CSP, frontend hosting,
dependency security, shared-device behavior, and session duration. Account
deactivation takes effect immediately; completed password recovery revokes all
existing signed-in sessions. In-process background email delivery is not a durable
mail queue and must be monitored; timing and concurrency abuse defenses still need
a production deployment review.
