#!/usr/bin/env python3
"""
Simple migration verification test
Verifies that the refactored modules can be imported correctly
"""
import sys
import importlib.util

def test_import(module_name, file_path):
    """Test if a module can be imported"""
    try:
        spec = importlib.util.spec_from_file_location(module_name, file_path)
        if spec is None:
            print(f"❌ Failed to load spec for {module_name} from {file_path}")
            return False
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
        print(f"✅ Successfully imported {module_name}")
        return True
    except Exception as e:
        print(f"❌ Failed to import {module_name}: {e}")
        return False

def main():
    """Main test function"""
    print("=" * 60)
    print("Testing refactored module imports")
    print("=" * 60)
    
    tests = [
        ("models", "models.py"),
        ("config", "config.py"),
        ("memory_graph", "memory_graph.py"),
        ("batch_extractor", "batch_extractor.py"),
    ]
    
    results = []
    for module_name, file_path in tests:
        results.append(test_import(module_name, file_path))
    
    print("=" * 60)
    if all(results):
        print("✅ All migration tests passed!")
        print("=" * 60)
        sys.exit(0)
    else:
        print("❌ Some migration tests failed!")
        print("=" * 60)
        sys.exit(1)

if __name__ == "__main__":
    main()
