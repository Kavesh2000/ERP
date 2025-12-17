#!/usr/bin/env python3
"""
Test script to verify bottle price is correctly added to order totals.
"""
import sys
import json
from pathlib import Path

# Add the workspace to path
sys.path.insert(0, str(Path(__file__).parent))

import db

def test_bottle_price_in_total():
    """Test that bottle price is added to the order total when use_bottle=True"""
    
    # Use the existing database (no db_path means it uses water.db in current dir)
    test_db = None  # Use default
    
    try:
        # Get a water product (assuming it exists)
        conn = db.connect(test_db)
        cur = conn.cursor()
        cur.execute("SELECT id, unit_price FROM products WHERE name LIKE '%5L water%' LIMIT 1")
        product = cur.fetchone()
        if not product:
            print("❌ No 5L water product found")
            return False
        
        product_id, product_price = product[0], float(product[1])
        print(f"✓ Found product ID {product_id} with price {product_price} KSH")
        
        # Get bottle product and update its price to 50 for testing
        cur.execute("SELECT id, unit_price FROM products WHERE name = 'Empty 5L bottle' LIMIT 1")
        bottle = cur.fetchone()
        if not bottle:
            print("❌ No bottle product found")
            return False
        
        bottle_id, _ = bottle[0], float(bottle[1])
        bottle_price = 50.0  # Set bottle price to 50 for testing
        cur.execute("UPDATE products SET unit_price = ? WHERE id = ?", (bottle_price, bottle_id))
        conn.commit()
        print(f"✓ Found bottle ID {bottle_id}, set price to {bottle_price} KSH for testing")
        
        conn.close()
        
        # Test 1: Order without bottle
        print("\n--- Test 1: Order without bottle ---")
        order1 = db.record_order(
            product_id=product_id,
            quantity=2,
            use_bottle=False,
            bottle_price=0,
            db_path=None
        )
        expected_total_1 = product_price * 2
        actual_total_1 = float(order1['total'])
        print(f"Quantity: 2, Product price: {product_price}")
        print(f"Expected total: {expected_total_1}, Actual: {actual_total_1}")
        if abs(actual_total_1 - expected_total_1) < 0.01:
            print("✓ Test 1 PASSED")
        else:
            print("❌ Test 1 FAILED")
            return False
        
        # Test 2: Order with bottle
        print("\n--- Test 2: Order with bottle ---")
        order2 = db.record_order(
            product_id=product_id,
            quantity=2,
            use_bottle=True,
            bottle_price=bottle_price,
            db_path=None
        )
        # Expected: (product_price * 2) + (bottle_price * 2)
        # Since quantity is 2, bottles_count should be 2
        expected_total_2 = (product_price * 2) + (bottle_price * 2)
        actual_total_2 = float(order2['total'])
        print(f"Quantity: 2, Product price: {product_price}, Bottle price: {bottle_price}")
        print(f"Expected total: {expected_total_2}, Actual: {actual_total_2}")
        if abs(actual_total_2 - expected_total_2) < 0.01:
            print("✓ Test 2 PASSED")
        else:
            print("❌ Test 2 FAILED")
            return False
        
        # Test 3: Verify bottle_price is stored in database
        print("\n--- Test 3: Verify bottle_price is stored ---")
        conn = db.connect(None)
        cur = conn.cursor()
        cur.execute("SELECT bottle_price FROM sales WHERE id = ?", (order2['id'],))
        result = cur.fetchone()
        if result:
            stored_bottle_price = float(result[0])
            print(f"Stored bottle_price: {stored_bottle_price}")
            if abs(stored_bottle_price - bottle_price) < 0.01:
                print("✓ Test 3 PASSED")
            else:
                print("❌ Test 3 FAILED - stored price doesn't match")
                return False
        else:
            print("❌ Test 3 FAILED - could not retrieve bottle_price")
            return False
        
        conn.close()
        
        print("\n✅ ALL TESTS PASSED!")
        return True
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == '__main__':
    success = test_bottle_price_in_total()
    sys.exit(0 if success else 1)
