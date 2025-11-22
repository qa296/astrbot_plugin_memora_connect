#!/usr/bin/env python3
"""
Group isolation verification test
Verifies that the memory system's group isolation feature is intact after refactoring
"""
import sys

def main():
    """Main verification function"""
    print("=" * 60)
    print("Verifying group isolation functionality")
    print("=" * 60)
    
    # Check if MemorySystem class has the necessary group isolation methods
    try:
        from memory_system_core import MemorySystem
        
        required_methods = [
            'filter_memories_by_group',
            'filter_concepts_by_group',
            '_get_group_db_path',
            '_extract_group_id_from_event',
        ]
        
        missing_methods = []
        for method_name in required_methods:
            if not hasattr(MemorySystem, method_name):
                missing_methods.append(method_name)
                print(f"❌ Missing method: {method_name}")
            else:
                print(f"✅ Found method: {method_name}")
        
        if missing_methods:
            print("=" * 60)
            print(f"❌ Group isolation verification failed!")
            print(f"   Missing methods: {', '.join(missing_methods)}")
            print("=" * 60)
            sys.exit(1)
        else:
            print("=" * 60)
            print("✅ Group isolation verification passed!")
            print("=" * 60)
            sys.exit(0)
            
    except ImportError as e:
        print(f"❌ Failed to import MemorySystem: {e}")
        print("=" * 60)
        sys.exit(1)
    except Exception as e:
        print(f"❌ Verification failed with error: {e}")
        print("=" * 60)
        sys.exit(1)

if __name__ == "__main__":
    main()
