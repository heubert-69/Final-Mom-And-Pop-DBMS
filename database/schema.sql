-- ============================================================
-- DELIVERY MANAGEMENT SYSTEM - ORACLE SCHEMA
-- ============================================================

-- Clean up existing objects (safe re-run)
BEGIN
  FOR t IN (SELECT table_name FROM user_tables
            WHERE table_name IN ('DELIVERIES','ORDERS','DRIVERS','USERS','AUDIT_LOGS')) LOOP
    EXECUTE IMMEDIATE 'DROP TABLE ' || t.table_name || ' CASCADE CONSTRAINTS';
  END LOOP;
END;
/

BEGIN
  FOR s IN (SELECT sequence_name FROM user_sequences
            WHERE sequence_name IN (
              'USERS_SEQ','ORDERS_SEQ','DRIVERS_SEQ','DELIVERIES_SEQ','AUDIT_SEQ')) LOOP
    EXECUTE IMMEDIATE 'DROP SEQUENCE ' || s.sequence_name;
  END LOOP;
END;
/

-- ============================================================
-- SEQUENCES
-- ============================================================

CREATE SEQUENCE users_seq       START WITH 1 INCREMENT BY 1 NOCACHE NOCYCLE;
CREATE SEQUENCE orders_seq      START WITH 1000 INCREMENT BY 1 NOCACHE NOCYCLE;
CREATE SEQUENCE drivers_seq     START WITH 1 INCREMENT BY 1 NOCACHE NOCYCLE;
CREATE SEQUENCE deliveries_seq  START WITH 1 INCREMENT BY 1 NOCACHE NOCYCLE;
CREATE SEQUENCE audit_seq       START WITH 1 INCREMENT BY 1 NOCACHE NOCYCLE;

-- ============================================================
-- TABLES
-- ============================================================

CREATE TABLE users (
  id            NUMBER PRIMARY KEY,
  name          VARCHAR2(100)  NOT NULL,
  email         VARCHAR2(150)  NOT NULL UNIQUE,
  password_hash VARCHAR2(255)  NOT NULL,
  role          VARCHAR2(20)   NOT NULL CHECK (role IN ('customer','driver','admin')),
  is_active     NUMBER(1)      DEFAULT 1 NOT NULL,
  created_at    TIMESTAMP      DEFAULT SYSTIMESTAMP NOT NULL,
  updated_at    TIMESTAMP      DEFAULT SYSTIMESTAMP NOT NULL
);

CREATE TABLE drivers (
  id                  NUMBER PRIMARY KEY,
  user_id             NUMBER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  vehicle_type        VARCHAR2(50)  DEFAULT 'motorcycle',
  license_plate       VARCHAR2(20),
  availability_status VARCHAR2(20)  DEFAULT 'available'
                      CHECK (availability_status IN ('available','busy','offline')),
  total_deliveries    NUMBER DEFAULT 0,
  rating              NUMBER(3,2)   DEFAULT 5.0,
  created_at          TIMESTAMP     DEFAULT SYSTIMESTAMP NOT NULL
);

CREATE TABLE orders (
  id              NUMBER PRIMARY KEY,
  customer_id     NUMBER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  pickup_address  VARCHAR2(300) NOT NULL,
  dropoff_address VARCHAR2(300) NOT NULL,
  package_desc    VARCHAR2(500),
  status          VARCHAR2(30) DEFAULT 'pending'
                  CHECK (status IN ('pending','assigned','picked_up','in_transit','delivered','cancelled')),
  total_amount    NUMBER(10,2)  DEFAULT 0,
  notes           VARCHAR2(500),
  created_at      TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL,
  updated_at      TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL
);

CREATE TABLE deliveries (
  id                  NUMBER PRIMARY KEY,
  order_id            NUMBER NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
  driver_id           NUMBER REFERENCES drivers(id),
  status              VARCHAR2(30) DEFAULT 'assigned'
                      CHECK (status IN ('assigned','picked_up','in_transit','delivered','failed')),
  assigned_at         TIMESTAMP DEFAULT SYSTIMESTAMP,
  picked_up_at        TIMESTAMP,
  delivered_at        TIMESTAMP,
  driver_notes        VARCHAR2(500),
  estimated_minutes   NUMBER
);

CREATE TABLE audit_logs (
  id          NUMBER PRIMARY KEY,
  table_name  VARCHAR2(50),
  record_id   NUMBER,
  action      VARCHAR2(20),
  old_value   VARCHAR2(500),
  new_value   VARCHAR2(500),
  changed_by  NUMBER REFERENCES users(id),
  changed_at  TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL
);

-- ============================================================
-- INDEXES
-- ============================================================

CREATE INDEX idx_orders_customer    ON orders(customer_id);
CREATE INDEX idx_orders_status      ON orders(status);
CREATE INDEX idx_orders_created_at  ON orders(created_at);
CREATE INDEX idx_deliveries_order   ON deliveries(order_id);
CREATE INDEX idx_deliveries_driver  ON deliveries(driver_id);
CREATE INDEX idx_deliveries_status  ON deliveries(status);
CREATE INDEX idx_drivers_user       ON drivers(user_id);
CREATE INDEX idx_drivers_avail      ON drivers(availability_status);
CREATE INDEX idx_audit_table        ON audit_logs(table_name, record_id);

-- ============================================================
-- TRIGGERS - Auto ID generation via sequences
-- ============================================================

CREATE OR REPLACE TRIGGER trg_users_bi
  BEFORE INSERT ON users
  FOR EACH ROW
BEGIN
  IF :NEW.id IS NULL THEN
    :NEW.id := users_seq.NEXTVAL;
  END IF;
  :NEW.created_at := SYSTIMESTAMP;
  :NEW.updated_at := SYSTIMESTAMP;
END;
/

CREATE OR REPLACE TRIGGER trg_users_bu
  BEFORE UPDATE ON users
  FOR EACH ROW
BEGIN
  :NEW.updated_at := SYSTIMESTAMP;
END;
/

CREATE OR REPLACE TRIGGER trg_orders_bi
  BEFORE INSERT ON orders
  FOR EACH ROW
BEGIN
  IF :NEW.id IS NULL THEN
    :NEW.id := orders_seq.NEXTVAL;
  END IF;
  :NEW.created_at := SYSTIMESTAMP;
  :NEW.updated_at := SYSTIMESTAMP;
END;
/

CREATE OR REPLACE TRIGGER trg_orders_bu
  BEFORE UPDATE ON orders
  FOR EACH ROW
BEGIN
  :NEW.updated_at := SYSTIMESTAMP;
END;
/

CREATE OR REPLACE TRIGGER trg_drivers_bi
  BEFORE INSERT ON drivers
  FOR EACH ROW
BEGIN
  IF :NEW.id IS NULL THEN
    :NEW.id := drivers_seq.NEXTVAL;
  END IF;
END;
/

CREATE OR REPLACE TRIGGER trg_deliveries_bi
  BEFORE INSERT ON deliveries
  FOR EACH ROW
BEGIN
  IF :NEW.id IS NULL THEN
    :NEW.id := deliveries_seq.NEXTVAL;
  END IF;
  :NEW.assigned_at := SYSTIMESTAMP;
END;
/

CREATE OR REPLACE TRIGGER trg_audit_bi
  BEFORE INSERT ON audit_logs
  FOR EACH ROW
BEGIN
  IF :NEW.id IS NULL THEN
    :NEW.id := audit_seq.NEXTVAL;
  END IF;
END;
/

-- Audit trigger: log order status changes
CREATE OR REPLACE TRIGGER trg_orders_audit
  AFTER UPDATE OF status ON orders
  FOR EACH ROW
BEGIN
  INSERT INTO audit_logs (table_name, record_id, action, old_value, new_value, changed_at)
  VALUES ('ORDERS', :NEW.id, 'STATUS_CHANGE', :OLD.status, :NEW.status, SYSTIMESTAMP);
END;
/

-- ============================================================
-- SEED DATA - Default admin user
-- password: 'admin123' (bcrypt hash - populated by backend init)
-- ============================================================

INSERT INTO users (name, email, password_hash, role)
VALUES ('System Admin', 'admin@delivery.com',
        '$2b$12$placeholder_will_be_set_by_init', 'admin');

COMMIT;

PROMPT Schema created successfully.
