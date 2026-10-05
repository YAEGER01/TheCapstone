"""Prove the live Django database connection is TLS-encrypted.

Usage:
    python manage.py check_db_tls            # exit 0 + cipher, or exit 1
    python manage.py check_db_tls --require  # exit 1 unless encrypted

Reads SHOW STATUS LIKE 'Ssl_cipher' on the default connection: an empty
cipher means the DB wire (credentials + member PII) is plaintext.
"""
from django.core.management.base import BaseCommand, CommandError
from django.db import connection


class Command(BaseCommand):
    help = "Verify the MySQL connection negotiates TLS (non-empty Ssl_cipher)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--require", action="store_true",
            help="Exit non-zero when the connection is NOT encrypted.",
        )

    def handle(self, *args, **options):
        with connection.cursor() as cur:
            cur.execute("SHOW STATUS LIKE 'Ssl_cipher'")
            row = cur.fetchone()
        cipher = (row[1] if row else "") or ""
        if cipher:
            self.stdout.write(self.style.SUCCESS(f"DB TLS active (cipher: {cipher})"))
        else:
            msg = "DB connection is NOT encrypted (Ssl_cipher empty)."
            if options["require"]:
                raise CommandError(msg + " See deploy/mysql_tls_server.sql.")
            self.stdout.write(self.style.WARNING(msg))
