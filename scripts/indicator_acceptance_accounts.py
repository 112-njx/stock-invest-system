"""Create/clean disposable accounts for local indicator acceptance; never use real accounts."""
import argparse
import json
from pathlib import Path
import secrets
import sys
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'stock_backend'))
from app.core.security import hash_password
from app.models.user import User
from app.utils.db import get_session


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['create', 'cleanup'])
    parser.add_argument('--file', required=True, type=Path)
    args = parser.parse_args()
    if args.action == 'create':
        if args.file.exists():
            raise SystemExit('Existing fixture file: clean its accounts before creating another run')
        accounts = []
        with get_session() as db:
            for _ in range(2):
                password = secrets.token_urlsafe(24)
                user = User(username='indicator_accept_' + uuid4().hex[:16],
                            password_hash=hash_password(password), email_verified=True)
                db.add(user)
                db.flush()
                accounts.append(dict(id=user.id, username=user.username, password=password))
            args.file.parent.mkdir(parents=True, exist_ok=True)
            # Write before commit: a failed write rolls back the account transaction.
            args.file.write_text(json.dumps(dict(version=1, accounts=accounts)), encoding='utf-8')
            db.commit()
        print('Created 2 disposable acceptance accounts')
    else:
        if not args.file.exists():
            print('No acceptance accounts to clean')
            return
        value = json.loads(args.file.read_text(encoding='utf-8'))
        assert value['version'] == 1 and len(value['accounts']) == 2
        with get_session() as db:
            for account in value['accounts']:
                assert account['username'].startswith('indicator_accept_') and type(account['id']) is int
                db.query(User).filter(User.id == account['id'], User.username == account['username']).delete(synchronize_session=False)
            db.commit()
        args.file.unlink()
        print('Removed disposable accounts and temporary credentials')


if __name__ == '__main__':
    main()
