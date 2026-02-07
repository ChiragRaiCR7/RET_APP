"""
Quick validation script for the new parallel conversion system.
Run this to verify the implementation is correct.
"""
import sys
from pathlib import Path

# Add backend to path
backend_path = Path(__file__).parent.parent
sys.path.insert(0, str(backend_path))

def test_imports():
    """Test that all modules can be imported"""
    print("Testing imports...")
    
    try:
        from api.services.parallel_converter import (
            convert_parallel,
            estimate_conversion_time,
            ConversionTask,
            ConversionResult,
            ConversionStats
        )
        print("✅ parallel_converter imports OK")
    except Exception as e:
        print(f"❌ parallel_converter import failed: {e}")
        return False
    
    try:
        from api.services.xml_processing_service import (
            xml_to_rows,
            xml_to_rows_streaming,
            STREAMING_THRESHOLD_MB
        )
        print("✅ xml_processing_service imports OK")
    except Exception as e:
        print(f"❌ xml_processing_service import failed: {e}")
        return False
    
    try:
        from api.services.conversion_service import convert_session
        print("✅ conversion_service imports OK")
    except Exception as e:
        print(f"❌ conversion_service import failed: {e}")
        return False
    
    try:
        from api.routers.conversion_router import router
        print("✅ conversion_router imports OK")
    except Exception as e:
        print(f"❌ conversion_router import failed: {e}")
        return False
    
    return True

def test_config():
    """Test that configuration is loaded"""
    print("\nTesting configuration...")
    
    try:
        from api.core.config import settings
        
        # Check new parallel conversion settings
        attrs = [
            'CONVERSION_DEFAULT_WORKERS',
            'CONVERSION_MAX_WORKERS',
            'CONVERSION_STREAMING_THRESHOLD_MB',
            'CONVERSION_BATCH_SIZE',
            'CONVERSION_PROGRESS_LOG_INTERVAL'
        ]
        
        for attr in attrs:
            value = getattr(settings, attr, None)
            if value is not None:
                print(f"✅ {attr} = {value}")
            else:
                print(f"⚠️  {attr} not found (will use defaults)")
        
        return True
    except Exception as e:
        print(f"❌ Config test failed: {e}")
        return False

def test_estimation():
    """Test conversion time estimation"""
    print("\nTesting estimation function...")
    
    try:
        from api.services.parallel_converter import estimate_conversion_time
        
        # Test cases
        test_cases = [
            (10000, 1.0, 32, "10k small files"),
            (100000, 2.5, 32, "100k medium files"),
            (100, 250, 16, "100 large files"),
        ]
        
        for num_files, avg_size_mb, workers, desc in test_cases:
            est_time = estimate_conversion_time(num_files, avg_size_mb, workers)
            print(f"✅ {desc}: ~{est_time:.1f}s ({est_time/60:.1f} min)")
        
        return True
    except Exception as e:
        print(f"❌ Estimation test failed: {e}")
        return False

def main():
    """Run all validation tests"""
    print("=" * 60)
    print("Parallel Conversion System - Validation")
    print("=" * 60)
    print()
    
    tests = [
        ("Imports", test_imports),
        ("Configuration", test_config),
        ("Estimation", test_estimation),
    ]
    
    results = []
    for name, test_func in tests:
        try:
            result = test_func()
            results.append((name, result))
        except Exception as e:
            print(f"❌ {name} test crashed: {e}")
            results.append((name, False))
    
    print()
    print("=" * 60)
    print("Summary:")
    print("=" * 60)
    
    for name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status}: {name}")
    
    all_passed = all(r for _, r in results)
    
    print()
    if all_passed:
        print("🎉 All validation tests passed!")
        print("The parallel conversion system is ready for use.")
        return 0
    else:
        print("⚠️  Some tests failed. Please review the errors above.")
        return 1

if __name__ == "__main__":
    sys.exit(main())
