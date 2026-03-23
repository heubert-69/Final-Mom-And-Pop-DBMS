-- ============================================================
-- gvenzl/oracle-xe runs .sql files in /docker-entrypoint-initdb.d
-- as SYSDBA against the CDB, so we need to switch to the PDB
-- and create the user+schema all in one script.
-- ============================================================

-- Switch to the pluggable database
ALTER SESSION SET CONTAINER = XEPDB1;

-- ── Create application user ──────────────────────────────────
DECLARE
  v_count NUMBER;
BEGIN
  SELECT COUNT(*) INTO v_count FROM dba_users WHERE username = 'DELIVERY_USER';
  IF v_count = 0 THEN
    EXECUTE IMMEDIATE 'CREATE USER delivery_user IDENTIFIED BY OraclePass123
      DEFAULT TABLESPACE USERS TEMPORARY TABLESPACE TEMP QUOTA UNLIMITED ON USERS';
    EXECUTE IMMEDIATE 'GRANT CONNECT, RESOURCE TO delivery_user';
    EXECUTE IMMEDIATE 'GRANT CREATE VIEW, CREATE SYNONYM TO delivery_user';
    EXECUTE IMMEDIATE 'GRANT UNLIMITED TABLESPACE TO delivery_user';
  END IF;
END;
/

-- Switch context to delivery_user schema
ALTER SESSION SET CURRENT_SCHEMA = delivery_user;

-- ── Drop existing objects (safe re-run) ──────────────────────
BEGIN
  FOR t IN (SELECT table_name FROM all_tables
            WHERE owner = 'DELIVERY_USER'
            AND table_name IN ('DELIVERIES','ORDERS','DRIVERS','USERS','AUDIT_LOGS')) LOOP
    EXECUTE IMMEDIATE 'DROP TABLE DELIVERY_USER.' || t.table_name || ' CASCADE CONSTRAINTS';
  END LOOP;
END;
/

BEGIN
  FOR s IN (SELECT sequence_name FROM all_sequences
            WHERE sequence_owner = 'DELIVERY_USER'
            AND sequence_name IN ('USERS_SEQ','ORDERS_SEQ','DRIVERS_SEQ','DELIVERIES_SEQ','AUDIT_SEQ')) LOOP
    EXECUTE IMMEDIATE 'DROP SEQUENCE DELIVERY_USER.' || s.sequence_name;
  END LOOP;
END;
/

-- ── Sequences ─────────────────────────────────────────────────
CREATE SEQUENCE delivery_user.users_seq      START WITH 1    INCREMENT BY 1 NOCACHE NOCYCLE;
CREATE SEQUENCE delivery_user.orders_seq     START WITH 1000 INCREMENT BY 1 NOCACHE NOCYCLE;
CREATE SEQUENCE delivery_user.drivers_seq    START WITH 1    INCREMENT BY 1 NOCACHE NOCYCLE;
CREATE SEQUENCE delivery_user.deliveries_seq START WITH 1    INCREMENT BY 1 NOCACHE NOCYCLE;
CREATE SEQUENCE delivery_user.audit_seq      START WITH 1    INCREMENT BY 1 NOCACHE NOCYCLE;

-- ── Tables ────────────────────────────────────────────────────
CREATE TABLE delivery_user.users (
  id            NUMBER PRIMARY KEY,
  name          VARCHAR2(100)  NOT NULL,
  email         VARCHAR2(150)  NOT NULL UNIQUE,
  password_hash VARCHAR2(255)  NOT NULL,
  role          VARCHAR2(20)   NOT NULL CHECK (role IN ('customer','driver','admin')),
  is_active     NUMBER(1)      DEFAULT 1 NOT NULL,
  created_at    TIMESTAMP      DEFAULT SYSTIMESTAMP NOT NULL,
  updated_at    TIMESTAMP      DEFAULT SYSTIMESTAMP NOT NULL
);

CREATE TABLE delivery_user.drivers (
  id                  NUMBER PRIMARY KEY,
  user_id             NUMBER NOT NULL REFERENCES delivery_user.users(id) ON DELETE CASCADE,
  vehicle_type        VARCHAR2(50)  DEFAULT 'motorcycle',
  license_plate       VARCHAR2(20),
  availability_status VARCHAR2(20)  DEFAULT 'available'
                      CHECK (availability_status IN ('available','busy','offline')),
  total_deliveries    NUMBER DEFAULT 0,
  rating              NUMBER(3,2)   DEFAULT 5.0,
  created_at          TIMESTAMP     DEFAULT SYSTIMESTAMP NOT NULL
);

CREATE TABLE delivery_user.orders (
  id              NUMBER PRIMARY KEY,
  customer_id     NUMBER NOT NULL REFERENCES delivery_user.users(id) ON DELETE CASCADE,
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

CREATE TABLE delivery_user.deliveries (
  id                NUMBER PRIMARY KEY,
  order_id          NUMBER NOT NULL REFERENCES delivery_user.orders(id) ON DELETE CASCADE,
  driver_id         NUMBER REFERENCES delivery_user.drivers(id),
  status            VARCHAR2(30) DEFAULT 'assigned'
                    CHECK (status IN ('assigned','picked_up','in_transit','delivered','failed')),
  assigned_at       TIMESTAMP DEFAULT SYSTIMESTAMP,
  picked_up_at      TIMESTAMP,
  delivered_at      TIMESTAMP,
  driver_notes      VARCHAR2(500),
  estimated_minutes NUMBER
);

CREATE TABLE delivery_user.audit_logs (
  id          NUMBER PRIMARY KEY,
  table_name  VARCHAR2(50),
  record_id   NUMBER,
  action      VARCHAR2(20),
  old_value   VARCHAR2(500),
  new_value   VARCHAR2(500),
  changed_by  NUMBER,
  changed_at  TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL
);

-- ── Indexes ───────────────────────────────────────────────────
CREATE INDEX delivery_user.idx_orders_customer   ON delivery_user.orders(customer_id);
CREATE INDEX delivery_user.idx_orders_status     ON delivery_user.orders(status);
CREATE INDEX delivery_user.idx_deliveries_order  ON delivery_user.deliveries(order_id);
CREATE INDEX delivery_user.idx_deliveries_driver ON delivery_user.deliveries(driver_id);
CREATE INDEX delivery_user.idx_drivers_user      ON delivery_user.drivers(user_id);
CREATE INDEX delivery_user.idx_drivers_avail     ON delivery_user.drivers(availability_status);

-- ── Triggers ──────────────────────────────────────────────────
CREATE OR REPLACE TRIGGER delivery_user.trg_users_bi
  BEFORE INSERT ON delivery_user.users FOR EACH ROW
BEGIN
  IF :NEW.id IS NULL THEN :NEW.id := delivery_user.users_seq.NEXTVAL; END IF;
  :NEW.created_at := SYSTIMESTAMP; :NEW.updated_at := SYSTIMESTAMP;
END;
/

CREATE OR REPLACE TRIGGER delivery_user.trg_users_bu
  BEFORE UPDATE ON delivery_user.users FOR EACH ROW
BEGIN :NEW.updated_at := SYSTIMESTAMP; END;
/

CREATE OR REPLACE TRIGGER delivery_user.trg_orders_bi
  BEFORE INSERT ON delivery_user.orders FOR EACH ROW
BEGIN
  IF :NEW.id IS NULL THEN :NEW.id := delivery_user.orders_seq.NEXTVAL; END IF;
  :NEW.created_at := SYSTIMESTAMP; :NEW.updated_at := SYSTIMESTAMP;
END;
/

CREATE OR REPLACE TRIGGER delivery_user.trg_orders_bu
  BEFORE UPDATE ON delivery_user.orders FOR EACH ROW
BEGIN :NEW.updated_at := SYSTIMESTAMP; END;
/

CREATE OR REPLACE TRIGGER delivery_user.trg_drivers_bi
  BEFORE INSERT ON delivery_user.drivers FOR EACH ROW
BEGIN
  IF :NEW.id IS NULL THEN :NEW.id := delivery_user.drivers_seq.NEXTVAL; END IF;
END;
/

CREATE OR REPLACE TRIGGER delivery_user.trg_deliveries_bi
  BEFORE INSERT ON delivery_user.deliveries FOR EACH ROW
BEGIN
  IF :NEW.id IS NULL THEN :NEW.id := delivery_user.deliveries_seq.NEXTVAL; END IF;
  :NEW.assigned_at := SYSTIMESTAMP;
END;
/

CREATE OR REPLACE TRIGGER delivery_user.trg_audit_bi
  BEFORE INSERT ON delivery_user.audit_logs FOR EACH ROW
BEGIN
  IF :NEW.id IS NULL THEN :NEW.id := delivery_user.audit_seq.NEXTVAL; END IF;
END;
/

CREATE OR REPLACE TRIGGER delivery_user.trg_orders_audit
  AFTER UPDATE OF status ON delivery_user.orders FOR EACH ROW
BEGIN
  INSERT INTO delivery_user.audit_logs(table_name,record_id,action,old_value,new_value,changed_at)
  VALUES('ORDERS',:NEW.id,'STATUS_CHANGE',:OLD.status,:NEW.status,SYSTIMESTAMP);
END;
/

-- ── Stored Procedures ─────────────────────────────────────────
CREATE OR REPLACE PROCEDURE delivery_user.create_order(
  p_customer_id IN NUMBER, p_pickup IN VARCHAR2, p_dropoff IN VARCHAR2,
  p_desc IN VARCHAR2, p_amount IN NUMBER, p_notes IN VARCHAR2,
  p_order_id OUT NUMBER, p_msg OUT VARCHAR2
) AS
  v_role users.role%TYPE; v_active users.is_active%TYPE;
BEGIN
  BEGIN
    SELECT role, is_active INTO v_role, v_active FROM delivery_user.users WHERE id = p_customer_id;
  EXCEPTION WHEN NO_DATA_FOUND THEN p_order_id:=NULL; p_msg:='ERROR: Customer not found'; RETURN;
  END;
  IF v_role NOT IN ('customer','admin') THEN p_order_id:=NULL; p_msg:='ERROR: Not a customer'; RETURN; END IF;
  IF v_active=0 THEN p_order_id:=NULL; p_msg:='ERROR: Inactive account'; RETURN; END IF;
  INSERT INTO delivery_user.orders(customer_id,pickup_address,dropoff_address,package_desc,total_amount,notes,status)
  VALUES(p_customer_id,p_pickup,p_dropoff,p_desc,NVL(p_amount,0),p_notes,'pending') RETURNING id INTO p_order_id;
  COMMIT; p_msg:='SUCCESS: Order '||p_order_id||' created';
EXCEPTION WHEN OTHERS THEN ROLLBACK; p_order_id:=NULL; p_msg:='ERROR: '||SQLERRM;
END;
/

CREATE OR REPLACE PROCEDURE delivery_user.assign_driver(
  p_order_id IN NUMBER, p_driver_id IN NUMBER, p_admin_id IN NUMBER,
  p_delivery_id OUT NUMBER, p_msg OUT VARCHAR2
) AS
  v_ostatus VARCHAR2(30); v_davail VARCHAR2(20); v_duser NUMBER; v_existing NUMBER;
BEGIN
  BEGIN SELECT status INTO v_ostatus FROM delivery_user.orders WHERE id=p_order_id;
  EXCEPTION WHEN NO_DATA_FOUND THEN p_delivery_id:=NULL; p_msg:='ERROR: Order not found'; RETURN; END;
  IF v_ostatus!='pending' THEN p_delivery_id:=NULL; p_msg:='ERROR: Order not pending ('||v_ostatus||')'; RETURN; END IF;
  BEGIN SELECT availability_status,user_id INTO v_davail,v_duser FROM delivery_user.drivers WHERE id=p_driver_id;
  EXCEPTION WHEN NO_DATA_FOUND THEN p_delivery_id:=NULL; p_msg:='ERROR: Driver not found'; RETURN; END;
  IF v_davail!='available' THEN p_delivery_id:=NULL; p_msg:='ERROR: Driver not available'; RETURN; END IF;
  SELECT COUNT(*) INTO v_existing FROM delivery_user.deliveries WHERE order_id=p_order_id;
  IF v_existing>0 THEN p_delivery_id:=NULL; p_msg:='ERROR: Already assigned'; RETURN; END IF;
  INSERT INTO delivery_user.deliveries(order_id,driver_id,status,estimated_minutes)
  VALUES(p_order_id,p_driver_id,'assigned',30) RETURNING id INTO p_delivery_id;
  UPDATE delivery_user.orders SET status='assigned' WHERE id=p_order_id;
  UPDATE delivery_user.drivers SET availability_status='busy' WHERE id=p_driver_id;
  INSERT INTO delivery_user.audit_logs(table_name,record_id,action,old_value,new_value,changed_by)
  VALUES('ORDERS',p_order_id,'DRIVER_ASSIGNED','pending','assigned (driver:'||p_driver_id||')',p_admin_id);
  COMMIT; p_msg:='SUCCESS: Driver '||p_driver_id||' assigned, delivery '||p_delivery_id||' created';
EXCEPTION WHEN OTHERS THEN ROLLBACK; p_delivery_id:=NULL; p_msg:='ERROR: '||SQLERRM;
END;
/

CREATE OR REPLACE PROCEDURE delivery_user.update_delivery_status(
  p_delivery_id IN NUMBER, p_driver_user_id IN NUMBER,
  p_new_status IN VARCHAR2, p_notes IN VARCHAR2, p_msg OUT VARCHAR2
) AS
  v_cur VARCHAR2(30); v_did NUMBER; v_oid NUMBER; v_duser NUMBER; v_order_status VARCHAR2(30);
BEGIN
  BEGIN
    SELECT d.status,d.driver_id,d.order_id,dr.user_id INTO v_cur,v_did,v_oid,v_duser
    FROM delivery_user.deliveries d JOIN delivery_user.drivers dr ON dr.id=d.driver_id WHERE d.id=p_delivery_id;
  EXCEPTION WHEN NO_DATA_FOUND THEN p_msg:='ERROR: Delivery not found'; RETURN; END;
  IF v_duser!=p_driver_user_id THEN
    DECLARE v_role VARCHAR2(20); BEGIN
      SELECT role INTO v_role FROM delivery_user.users WHERE id=p_driver_user_id;
      IF v_role!='admin' THEN p_msg:='ERROR: Not authorized'; RETURN; END IF;
    END;
  END IF;
  IF NOT((v_cur='assigned' AND p_new_status IN ('picked_up','failed')) OR
         (v_cur='picked_up' AND p_new_status IN ('in_transit','failed')) OR
         (v_cur='in_transit' AND p_new_status IN ('delivered','failed')))
  THEN p_msg:='ERROR: Invalid transition '||v_cur||' -> '||p_new_status; RETURN; END IF;
  v_order_status:=CASE p_new_status WHEN 'picked_up' THEN 'picked_up'
    WHEN 'in_transit' THEN 'in_transit' WHEN 'delivered' THEN 'delivered' ELSE 'cancelled' END;
  UPDATE delivery_user.deliveries SET status=p_new_status, driver_notes=p_notes,
    picked_up_at=CASE WHEN p_new_status='picked_up' THEN SYSTIMESTAMP ELSE picked_up_at END,
    delivered_at=CASE WHEN p_new_status='delivered' THEN SYSTIMESTAMP ELSE delivered_at END
  WHERE id=p_delivery_id;
  UPDATE delivery_user.orders SET status=v_order_status WHERE id=v_oid;
  IF p_new_status IN ('delivered','failed') THEN
    UPDATE delivery_user.drivers SET availability_status='available',
      total_deliveries=total_deliveries+CASE WHEN p_new_status='delivered' THEN 1 ELSE 0 END
    WHERE id=v_did;
  END IF;
  COMMIT; p_msg:='SUCCESS: Delivery '||p_delivery_id||' -> '||p_new_status;
EXCEPTION WHEN OTHERS THEN ROLLBACK; p_msg:='ERROR: '||SQLERRM;
END;
/

CREATE OR REPLACE PROCEDURE delivery_user.cancel_order(
  p_order_id IN NUMBER, p_user_id IN NUMBER, p_msg OUT VARCHAR2
) AS
  v_status VARCHAR2(30); v_cust NUMBER; v_role VARCHAR2(20); v_did NUMBER;
BEGIN
  SELECT o.status,o.customer_id,u.role INTO v_status,v_cust,v_role
  FROM delivery_user.orders o JOIN delivery_user.users u ON u.id=p_user_id WHERE o.id=p_order_id;
  IF v_role='customer' AND v_cust!=p_user_id THEN p_msg:='ERROR: Not authorized'; RETURN; END IF;
  IF v_status NOT IN ('pending','assigned') THEN p_msg:='ERROR: Cannot cancel: '||v_status; RETURN; END IF;
  BEGIN
    SELECT driver_id INTO v_did FROM delivery_user.deliveries WHERE order_id=p_order_id;
    UPDATE delivery_user.drivers SET availability_status='available' WHERE id=v_did;
    DELETE FROM delivery_user.deliveries WHERE order_id=p_order_id;
  EXCEPTION WHEN NO_DATA_FOUND THEN NULL; END;
  UPDATE delivery_user.orders SET status='cancelled' WHERE id=p_order_id;
  COMMIT; p_msg:='SUCCESS: Order '||p_order_id||' cancelled';
EXCEPTION WHEN OTHERS THEN ROLLBACK; p_msg:='ERROR: '||SQLERRM;
END;
/

CREATE OR REPLACE FUNCTION delivery_user.get_available_driver RETURN NUMBER AS
  v_id NUMBER;
BEGIN
  SELECT id INTO v_id FROM (
    SELECT id FROM delivery_user.drivers WHERE availability_status='available'
    ORDER BY total_deliveries ASC, id ASC
  ) WHERE ROWNUM=1;
  RETURN v_id;
EXCEPTION WHEN NO_DATA_FOUND THEN RETURN NULL;
END;
/

-- ── Analytics Views ───────────────────────────────────────────
CREATE OR REPLACE VIEW delivery_user.v_order_summary AS
SELECT o.id order_id, u.name customer_name, u.email customer_email,
  o.pickup_address, o.dropoff_address, o.package_desc, o.status order_status,
  o.total_amount, o.created_at, o.updated_at, du.name driver_name,
  d.status delivery_status, d.assigned_at, d.picked_up_at, d.delivered_at,
  CASE WHEN d.delivered_at IS NOT NULL AND d.assigned_at IS NOT NULL
    THEN ROUND((CAST(d.delivered_at AS DATE)-CAST(d.assigned_at AS DATE))*24*60,1) END delivery_minutes
FROM delivery_user.orders o JOIN delivery_user.users u ON u.id=o.customer_id
LEFT JOIN delivery_user.deliveries d ON d.order_id=o.id
LEFT JOIN delivery_user.drivers dr ON dr.id=d.driver_id
LEFT JOIN delivery_user.users du ON du.id=dr.user_id;

-- ── Seed admin user ───────────────────────────────────────────
-- Password hash is set by the backend on first startup
INSERT INTO delivery_user.users(name,email,password_hash,role)
VALUES('System Admin','admin@delivery.com','$2b$12$placeholder_will_be_replaced_by_init','admin');
COMMIT;

PROMPT === DeliverPH schema initialized successfully ===
