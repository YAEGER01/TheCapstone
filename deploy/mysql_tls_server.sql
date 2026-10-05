-- ============================================================================
-- MySQL TLS server-side setup (run ONCE on the database server as root).
-- Pairs with the Django side: DB_SSL_CA/CERT/KEY (+ optional DB_SSL_ENFORCE)
-- in caufa_portal/settings.py, and .env.example "MySQL TLS" section.
--
-- 1. Generate server + client certs (on the DB host):
--      sudo mysql_ssl_rsa_setup --datadir=/var/lib/mysql --uid=mysql
--    (or openssl equivalent; skip if your distro already ships them)
-- 2. Enable TLS in my.cnf — see deploy/mysql_tls.cnf snippet.
-- 3. Restart MySQL, then run the statements below.
-- ============================================================================

-- Prove the server actually offers TLS (both must say YES):
SHOW VARIABLES WHERE Variable_name IN ('have_ssl', 'have_openssl');

-- Force the app account onto TLS. Adjust 'caufa_app'@'%' to your DB_USER
-- and host pattern. REQUIRE SSL = encrypted; REQUIRE X509 = encrypted AND
-- the client must present a cert signed by the server CA (use X509 once
-- DB_SSL_CERT/DB_SSL_KEY are deployed to Django).
--   ALTER USER 'caufa_app'@'%' REQUIRE X509;
ALTER USER 'caufa_app'@'%' REQUIRE SSL;

-- Belt and suspenders: refuse ALL plaintext clients server-wide.
-- (Equivalent my.cnf: require_secure_transport=ON — see mysql_tls.cnf.)
-- SET PERSIST require_secure_transport = ON;

-- Verify: expect one row per account, ssl_type = SSL or X509 (never empty).
SELECT user, host, ssl_type FROM mysql.user ORDER BY user, host;

-- From the Django host, confirm the live session is encrypted
-- (also automated by: python manage.py check_db_tls):
--   SHOW STATUS LIKE 'Ssl_cipher';   -- non-empty cipher = encrypted
