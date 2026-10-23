"""Explicit local-only tools for synthetic development accounts."""
import argparse
from getpass import getpass
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.api.auth import Registration, hasher
from app.core.config import get_settings
from app.db.session import engine
from app.models import Student
from app.models.auth import User
from app.models.conversation import utc_now


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    counselor = commands.add_parser('create-counselor')
    counselor.add_argument('--email', required=True)
    link = commands.add_parser('link-synthetic-student')
    link.add_argument('--email', required=True)
    link.add_argument('--student-id', type=int, required=True)
    parser.add_argument('--synthetic-data-only', action='store_true', required=True)
    args = parser.parse_args()
    settings = get_settings()
    if settings.environment != 'development' or not settings.auth_dev_commands:
        parser.error('Requires ENVIRONMENT=development and AUTH_DEV_COMMANDS=true')
    password = getpass('New account password (12–128 characters): ')
    if password != getpass('Confirm password: '):
        parser.error('Passwords do not match')
    credentials = Registration(email=args.email, password=password)
    with Session(engine) as db:
        if db.scalar(select(User.id).where(User.email == credentials.email)):
            parser.error('Account already exists; this command never reassigns an account')
        student_id = None
        if args.command == 'link-synthetic-student':
            student_id = args.student_id
            if not db.get(Student, student_id) or db.scalar(select(User.id).where(User.student_id == student_id)):
                parser.error('Student does not exist or is already linked')
        db.add(User(email=credentials.email, password_hash=hasher.hash(password),
                    role='counselor' if student_id is None else 'student', student_id=student_id,
                    email_verified_at=utc_now()))
        db.commit()
    print('Development account created. No existing records were modified.')


if __name__ == '__main__':
    main()
