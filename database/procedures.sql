-- ============================================================
-- DELIVERY MANAGEMENT SYSTEM - STORED PROCEDURES
-- ============================================================

-- ============================================================
-- PROCEDURE: create_order
-- Creates a new order for a customer
-- ============================================================

CREATE OR REPLACE PROCEDURE create_order (
  p_customer_id     IN  orders.customer_id%TYPE,
  p_pickup_address  IN  orders.pickup_address%TYPE,
  p_dropoff_address IN  orders.dropoff_address%TYPE,
  p_package_desc    IN  orders.package_desc%TYPE,
  p_total_amount    IN  orders.total_amount%TYPE,
  p_notes           IN  orders.notes%TYPE,
  p_order_id        OUT orders.id%TYPE,
  p_status_msg      OUT VARCHAR2
) AS
  v_customer_role users.role%TYPE;
  v_is_active     users.is_active%TYPE;
BEGIN
  -- Validate customer exists and is active
  BEGIN
    SELECT role, is_active INTO v_customer_role, v_is_active
    FROM users WHERE id = p_customer_id;
  EXCEPTION
    WHEN NO_DATA_FOUND THEN
      p_order_id   := NULL;
      p_status_msg := 'ERROR: Customer not found';
      RETURN;
  END;

  IF v_customer_role NOT IN ('customer', 'admin') THEN
    p_order_id   := NULL;
    p_status_msg := 'ERROR: User is not a customer';
    RETURN;
  END IF;

  IF v_is_active = 0 THEN
    p_order_id   := NULL;
    p_status_msg := 'ERROR: Customer account is inactive';
    RETURN;
  END IF;

  -- Insert order (trigger handles ID + timestamps)
  INSERT INTO orders (customer_id, pickup_address, dropoff_address,
                      package_desc, total_amount, notes, status)
  VALUES (p_customer_id, p_pickup_address, p_dropoff_address,
          p_package_desc, NVL(p_total_amount, 0), p_notes, 'pending')
  RETURNING id INTO p_order_id;

  COMMIT;
  p_status_msg := 'SUCCESS: Order ' || p_order_id || ' created';

EXCEPTION
  WHEN OTHERS THEN
    ROLLBACK;
    p_order_id   := NULL;
    p_status_msg := 'ERROR: ' || SQLERRM;
END create_order;
/

-- ============================================================
-- PROCEDURE: assign_driver
-- Assigns an available driver to a pending order
-- ============================================================

CREATE OR REPLACE PROCEDURE assign_driver (
  p_order_id    IN  orders.id%TYPE,
  p_driver_id   IN  drivers.id%TYPE,
  p_admin_id    IN  users.id%TYPE,
  p_delivery_id OUT deliveries.id%TYPE,
  p_status_msg  OUT VARCHAR2
) AS
  v_order_status      orders.status%TYPE;
  v_driver_avail      drivers.availability_status%TYPE;
  v_driver_user_id    drivers.user_id%TYPE;
  v_existing_delivery NUMBER;
BEGIN
  -- Validate order exists and is pending
  BEGIN
    SELECT status INTO v_order_status FROM orders WHERE id = p_order_id;
  EXCEPTION
    WHEN NO_DATA_FOUND THEN
      p_delivery_id := NULL;
      p_status_msg  := 'ERROR: Order not found';
      RETURN;
  END;

  IF v_order_status != 'pending' THEN
    p_delivery_id := NULL;
    p_status_msg  := 'ERROR: Order is not in pending status (current: ' || v_order_status || ')';
    RETURN;
  END IF;

  -- Validate driver exists and is available
  BEGIN
    SELECT availability_status, user_id
    INTO v_driver_avail, v_driver_user_id
    FROM drivers WHERE id = p_driver_id;
  EXCEPTION
    WHEN NO_DATA_FOUND THEN
      p_delivery_id := NULL;
      p_status_msg  := 'ERROR: Driver not found';
      RETURN;
  END;

  IF v_driver_avail != 'available' THEN
    p_delivery_id := NULL;
    p_status_msg  := 'ERROR: Driver is not available (status: ' || v_driver_avail || ')';
    RETURN;
  END IF;

  -- Check no existing delivery for this order
  SELECT COUNT(*) INTO v_existing_delivery
  FROM deliveries WHERE order_id = p_order_id;

  IF v_existing_delivery > 0 THEN
    p_delivery_id := NULL;
    p_status_msg  := 'ERROR: Order already has an assigned delivery';
    RETURN;
  END IF;

  -- Create delivery record
  INSERT INTO deliveries (order_id, driver_id, status, estimated_minutes)
  VALUES (p_order_id, p_driver_id, 'assigned', 30)
  RETURNING id INTO p_delivery_id;

  -- Update order status
  UPDATE orders SET status = 'assigned' WHERE id = p_order_id;

  -- Mark driver as busy
  UPDATE drivers SET availability_status = 'busy' WHERE id = p_driver_id;

  -- Audit log
  INSERT INTO audit_logs (table_name, record_id, action, old_value, new_value, changed_by)
  VALUES ('ORDERS', p_order_id, 'DRIVER_ASSIGNED',
          'pending', 'assigned (driver: ' || p_driver_id || ')', p_admin_id);

  COMMIT;
  p_status_msg := 'SUCCESS: Driver ' || p_driver_id || ' assigned, delivery ' || p_delivery_id || ' created';

EXCEPTION
  WHEN OTHERS THEN
    ROLLBACK;
    p_delivery_id := NULL;
    p_status_msg  := 'ERROR: ' || SQLERRM;
END assign_driver;
/

-- ============================================================
-- PROCEDURE: update_delivery_status
-- Driver updates delivery status through the lifecycle
-- ============================================================

CREATE OR REPLACE PROCEDURE update_delivery_status (
  p_delivery_id   IN  deliveries.id%TYPE,
  p_driver_user_id IN users.id%TYPE,
  p_new_status    IN  deliveries.status%TYPE,
  p_driver_notes  IN  deliveries.driver_notes%TYPE,
  p_status_msg    OUT VARCHAR2
) AS
  v_current_status  deliveries.status%TYPE;
  v_driver_id       deliveries.driver_id%TYPE;
  v_driver_user     drivers.user_id%TYPE;
  v_order_id        deliveries.order_id%TYPE;
  v_new_order_status orders.status%TYPE;
BEGIN
  -- Get delivery details
  BEGIN
    SELECT d.status, d.driver_id, d.order_id, dr.user_id
    INTO v_current_status, v_driver_id, v_order_id, v_driver_user
    FROM deliveries d
    JOIN drivers dr ON dr.id = d.driver_id
    WHERE d.id = p_delivery_id;
  EXCEPTION
    WHEN NO_DATA_FOUND THEN
      p_status_msg := 'ERROR: Delivery not found';
      RETURN;
  END;

  -- Verify driver owns this delivery
  IF v_driver_user != p_driver_user_id THEN
    -- Check if admin (allow admin override)
    DECLARE
      v_role users.role%TYPE;
    BEGIN
      SELECT role INTO v_role FROM users WHERE id = p_driver_user_id;
      IF v_role != 'admin' THEN
        p_status_msg := 'ERROR: Not authorized for this delivery';
        RETURN;
      END IF;
    END;
  END IF;

  -- Validate status transition
  IF NOT (
    (v_current_status = 'assigned'   AND p_new_status IN ('picked_up','failed')) OR
    (v_current_status = 'picked_up'  AND p_new_status IN ('in_transit','failed')) OR
    (v_current_status = 'in_transit' AND p_new_status IN ('delivered','failed'))
  ) THEN
    p_status_msg := 'ERROR: Invalid transition ' || v_current_status || ' -> ' || p_new_status;
    RETURN;
  END IF;

  -- Map delivery status to order status
  v_new_order_status := CASE p_new_status
    WHEN 'picked_up'  THEN 'picked_up'
    WHEN 'in_transit' THEN 'in_transit'
    WHEN 'delivered'  THEN 'delivered'
    WHEN 'failed'     THEN 'cancelled'
  END;

  -- Update delivery with timestamp
  UPDATE deliveries
  SET status       = p_new_status,
      driver_notes = p_driver_notes,
      picked_up_at  = CASE WHEN p_new_status = 'picked_up'  THEN SYSTIMESTAMP ELSE picked_up_at  END,
      delivered_at  = CASE WHEN p_new_status = 'delivered'  THEN SYSTIMESTAMP ELSE delivered_at  END
  WHERE id = p_delivery_id;

  -- Update order status
  UPDATE orders SET status = v_new_order_status WHERE id = v_order_id;

  -- If delivered or failed, free up the driver
  IF p_new_status IN ('delivered', 'failed') THEN
    UPDATE drivers
    SET availability_status = 'available',
        total_deliveries = total_deliveries + CASE WHEN p_new_status = 'delivered' THEN 1 ELSE 0 END
    WHERE id = v_driver_id;
  END IF;

  COMMIT;
  p_status_msg := 'SUCCESS: Delivery ' || p_delivery_id || ' updated to ' || p_new_status;

EXCEPTION
  WHEN OTHERS THEN
    ROLLBACK;
    p_status_msg := 'ERROR: ' || SQLERRM;
END update_delivery_status;
/

-- ============================================================
-- PROCEDURE: cancel_order
-- Cancels a pending or assigned order
-- ============================================================

CREATE OR REPLACE PROCEDURE cancel_order (
  p_order_id   IN  orders.id%TYPE,
  p_user_id    IN  users.id%TYPE,
  p_status_msg OUT VARCHAR2
) AS
  v_status      orders.status%TYPE;
  v_customer_id orders.customer_id%TYPE;
  v_user_role   users.role%TYPE;
  v_driver_id   deliveries.driver_id%TYPE;
BEGIN
  SELECT o.status, o.customer_id, u.role
  INTO v_status, v_customer_id, v_user_role
  FROM orders o JOIN users u ON u.id = p_user_id
  WHERE o.id = p_order_id;

  -- Only the customer who placed it or an admin can cancel
  IF v_user_role = 'customer' AND v_customer_id != p_user_id THEN
    p_status_msg := 'ERROR: Not authorized to cancel this order';
    RETURN;
  END IF;

  IF v_status NOT IN ('pending', 'assigned') THEN
    p_status_msg := 'ERROR: Cannot cancel order in status: ' || v_status;
    RETURN;
  END IF;

  -- Free driver if assigned
  BEGIN
    SELECT driver_id INTO v_driver_id
    FROM deliveries WHERE order_id = p_order_id;

    UPDATE drivers SET availability_status = 'available' WHERE id = v_driver_id;
    DELETE FROM deliveries WHERE order_id = p_order_id;
  EXCEPTION
    WHEN NO_DATA_FOUND THEN NULL;
  END;

  UPDATE orders SET status = 'cancelled' WHERE id = p_order_id;
  COMMIT;
  p_status_msg := 'SUCCESS: Order ' || p_order_id || ' cancelled';

EXCEPTION
  WHEN OTHERS THEN
    ROLLBACK;
    p_status_msg := 'ERROR: ' || SQLERRM;
END cancel_order;
/

-- ============================================================
-- FUNCTION: get_available_driver
-- Returns the best available driver (least deliveries)
-- ============================================================

CREATE OR REPLACE FUNCTION get_available_driver RETURN NUMBER AS
  v_driver_id drivers.id%TYPE;
BEGIN
  SELECT id INTO v_driver_id
  FROM (
    SELECT d.id, d.total_deliveries
    FROM drivers d
    WHERE d.availability_status = 'available'
    ORDER BY d.total_deliveries ASC, d.id ASC
  )
  WHERE ROWNUM = 1;

  RETURN v_driver_id;
EXCEPTION
  WHEN NO_DATA_FOUND THEN
    RETURN NULL;
END get_available_driver;
/

-- ============================================================
-- ANALYTICS VIEW
-- ============================================================

CREATE OR REPLACE VIEW v_order_summary AS
SELECT
  o.id              AS order_id,
  u.name            AS customer_name,
  u.email           AS customer_email,
  o.pickup_address,
  o.dropoff_address,
  o.package_desc,
  o.status          AS order_status,
  o.total_amount,
  o.created_at,
  o.updated_at,
  du.name           AS driver_name,
  d.status          AS delivery_status,
  d.assigned_at,
  d.picked_up_at,
  d.delivered_at,
  CASE
    WHEN d.delivered_at IS NOT NULL AND d.assigned_at IS NOT NULL
    THEN ROUND((CAST(d.delivered_at AS DATE) - CAST(d.assigned_at AS DATE)) * 24 * 60, 1)
    ELSE NULL
  END               AS delivery_minutes
FROM orders o
JOIN users u ON u.id = o.customer_id
LEFT JOIN deliveries d ON d.order_id = o.id
LEFT JOIN drivers dr ON dr.id = d.driver_id
LEFT JOIN users du ON du.id = dr.user_id;

-- ============================================================
-- ANALYTICS VIEW: Driver performance
-- ============================================================

CREATE OR REPLACE VIEW v_driver_stats AS
SELECT
  dr.id             AS driver_id,
  u.name            AS driver_name,
  u.email,
  dr.vehicle_type,
  dr.availability_status,
  dr.total_deliveries,
  dr.rating,
  COUNT(d.id)       AS active_deliveries,
  AVG(CASE
    WHEN d.delivered_at IS NOT NULL AND d.assigned_at IS NOT NULL
    THEN ROUND((CAST(d.delivered_at AS DATE) - CAST(d.assigned_at AS DATE)) * 24 * 60, 1)
  END)              AS avg_delivery_minutes
FROM drivers dr
JOIN users u ON u.id = dr.user_id
LEFT JOIN deliveries d ON d.driver_id = dr.id
GROUP BY dr.id, u.name, u.email, dr.vehicle_type,
         dr.availability_status, dr.total_deliveries, dr.rating;

PROMPT Procedures, functions, and views created successfully.
