-- Stored Procedures for Manufacturing Module

DELIMITER $$

-- Preview FEFO Issue (shows which batches would be used)
CREATE PROCEDURE IF NOT EXISTS `sp_preview_fefo_issue`(
    IN p_product_id BIGINT,
    IN p_quantity DECIMAL(10,2),
    IN p_warehouse_id INT
)
BEGIN
    SELECT 
        batch_no,
        SUM(remain) as available_qty,
        expired_date,
        CASE 
            WHEN expired_date < CURDATE() THEN 'EXPIRED'
            WHEN expired_date <= DATE_ADD(CURDATE(), INTERVAL 7 DAY) THEN 'CRITICAL'
            WHEN expired_date <= DATE_ADD(CURDATE(), INTERVAL 30 DAY) THEN 'WARNING'
            ELSE 'OK'
        END as expiry_status
    FROM inventory_histories
    WHERE product_id = p_product_id
    AND warehouse_id = p_warehouse_id
    AND remain > 0
    AND delete_flag = 0
    GROUP BY batch_no, expired_date
    ORDER BY expired_date ASC, batch_no ASC;
END$$

-- Issue Material using FEFO
CREATE PROCEDURE IF NOT EXISTS `sp_issue_material_fefo`(
    IN p_material_id BIGINT,
    IN p_quantity DECIMAL(10,4),
    IN p_warehouse_id INT,
    IN p_issue_id INT,
    IN p_manufacturing_order_id INT,
    IN p_group_id VARCHAR(255),
    IN p_user_id INT,
    IN p_allow_expired BOOLEAN
)
BEGIN
    DECLARE v_remaining_qty DECIMAL(10,4);
    DECLARE v_batch_no VARCHAR(50);
    DECLARE v_expired_date DATE;
    DECLARE v_available_qty DECIMAL(10,4);
    DECLARE v_inventory_id BIGINT;
    DECLARE v_take_qty DECIMAL(10,4);
    DECLARE done INT DEFAULT FALSE;
    
    -- Cursor for FEFO selection
    DECLARE batch_cursor CURSOR FOR
        SELECT 
            id,
            batch_no,
            expired_date,
            remain
        FROM inventory_histories
        WHERE product_id = p_material_id
        AND warehouse_id = p_warehouse_id
        AND remain > 0
        AND delete_flag = 0
        AND (p_allow_expired = TRUE OR expired_date >= CURDATE())
        ORDER BY expired_date ASC, batch_no ASC, id ASC;
    
    DECLARE CONTINUE HANDLER FOR NOT FOUND SET done = TRUE;
    
    SET v_remaining_qty = p_quantity;
    
    -- Start transaction
    START TRANSACTION;
    
    OPEN batch_cursor;
    
    read_loop: LOOP
        FETCH batch_cursor INTO v_inventory_id, v_batch_no, v_expired_date, v_available_qty;
        
        IF done OR v_remaining_qty <= 0 THEN
            LEAVE read_loop;
        END IF;
        
        -- Calculate quantity to take from this batch
        SET v_take_qty = LEAST(v_remaining_qty, v_available_qty);
        
        -- Insert material issue detail
        INSERT INTO material_issue_details (
            material_issue_id,
            material_id,
            quantity,
            uom,
            batch_no,
            inventory_history_id,
            manufacturing_order_id,
            created_date
        )
        SELECT 
            p_issue_id,
            p_material_id,
            v_take_qty,
            p.uom,
            v_batch_no,
            v_inventory_id,
            p_manufacturing_order_id,
            NOW()
        FROM products p
        WHERE p.id = p_material_id;
        
        -- Update inventory remain
        UPDATE inventory_histories
        SET remain = remain - v_take_qty,
            updated_date = NOW()
        WHERE id = v_inventory_id;
        
        -- Insert stock out record
        INSERT INTO inventory_histories (
            type,
            product_id,
            warehouse_id,
            quantity,
            remain,
            batch_no,
            expired_date,
            action_detail_id,
            group_id,
            created_by,
            created_date,
            delete_flag
        )
        VALUES (
            'stockOutProduction',
            p_material_id,
            p_warehouse_id,
            -v_take_qty,
            0,
            v_batch_no,
            v_expired_date,
            LAST_INSERT_ID(),
            p_group_id,
            p_user_id,
            NOW(),
            0
        );
        
        -- Update remaining quantity
        SET v_remaining_qty = v_remaining_qty - v_take_qty;
        
    END LOOP;
    
    CLOSE batch_cursor;
    
    -- Check if all quantity was issued
    IF v_remaining_qty > 0 THEN
        ROLLBACK;
        SIGNAL SQLSTATE '45000' 
        SET MESSAGE_TEXT = 'Insufficient stock to complete material issue';
    ELSE
        COMMIT;
    END IF;
    
END$$

DELIMITER ;