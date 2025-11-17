"""
简单的语法和结构检查
"""

import ast
import sys

def check_file(filepath):
    """检查文件语法"""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            code = f.read()
        ast.parse(code)
        print(f"✓ {filepath}: 语法正确")
        return True
    except SyntaxError as e:
        print(f"✗ {filepath}: 语法错误 - {e}")
        return False
    except Exception as e:
        print(f"✗ {filepath}: 检查失败 - {e}")
        return False

def main():
    """主检查函数"""
    files = [
        "memory_events.py",
        "topic_engine.py",
        "user_profiling.py",
        "temporal_memory.py",
        "memory_api_gateway.py"
    ]
    
    print("=" * 60)
    print("Memora Connect 升级模块语法检查")
    print("=" * 60)
    
    all_passed = True
    for filepath in files:
        if not check_file(filepath):
            all_passed = False
    
    print("=" * 60)
    if all_passed:
        print("✅ 所有文件语法检查通过！")
        
        # 统计代码行数
        total_lines = 0
        for filepath in files:
            with open(filepath, 'r', encoding='utf-8') as f:
                lines = len(f.readlines())
                total_lines += lines
                print(f"  - {filepath}: {lines} 行")
        
        print(f"\n总计新增代码: {total_lines} 行")
        print("\n新增功能模块:")
        print("  ✓ 事件总线系统 (memory_events.py)")
        print("  ✓ 话题计算引擎 (topic_engine.py)")
        print("  ✓ 用户画像系统 (user_profiling.py)")
        print("  ✓ 时间维度记忆 (temporal_memory.py)")
        print("  ✓ 统一API网关 (memory_api_gateway.py)")
        
        return 0
    else:
        print("❌ 部分文件语法检查失败")
        return 1

if __name__ == "__main__":
    sys.exit(main())
