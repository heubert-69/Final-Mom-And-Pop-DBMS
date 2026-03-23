-- ============================================================
-- Run this as SYSDBA / SYS to create the application user
-- ============================================================

-- Connect to pluggable database
ALTER SESSION SET CONTAINER = XEPDB1;

-- Create application user
CREATE USER delivery_user IDENTIFIED BY OraclePass123
  DEFAULT TABLESPACE USERS
  TEMPORARY TABLESPACE TEMP
  QUOTA UNLIMITED ON USERS;

-- Grant required privileges
GRANT CREATE SESSION TO delivery_user;
GRANT CREATE TABLE TO delivery_user;
GRANT CREATE SEQUENCE TO delivery_user;
GRANT CREATE TRIGGER TO delivery_user;
GRANT CREATE PROCEDURE TO delivery_user;
GRANT CREATE VIEW TO delivery_user;
GRANT CREATE SYNONYM TO delivery_user;

-- For Oracle XE free tier - also grant these
GRANT RESOURCE TO delivery_user;
GRANT CONNECT TO delivery_user;

COMMIT;

PROMPT User delivery_user created. Now run schema.sql and procedures.sql as delivery_user.
