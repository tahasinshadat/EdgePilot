"""Test script to verify all MCP tools are working correctly."""

from MCP.tool_executor import ToolExecutor

def test_tools():
    """Test all available tools."""
    executor = ToolExecutor()

    print("="*60)
    print("Testing EdgePilot MCP Tools")
    print("="*60)

    # Test 1: gather_metrics
    print("\n1. Testing gather_metrics...")
    result = executor.execute("gather_metrics", {"top_n": 5})
    if result["success"]:
        print("   [OK] gather_metrics works!")
        if 'processes' in result.get('result', {}):
            print(f"   Found {len(result['result']['processes'])} processes")
        else:
            print(f"   Result keys: {list(result.get('result', {}).keys())[:5]}")
    else:
        print(f"   [ERROR] {result.get('error')}")

    # Test 2: search
    print("\n2. Testing search (looking for 'notepad')...")
    result = executor.execute("search", {"app_name": "notepad"})
    if result["success"]:
        print("   [OK] search works!")
        print(f"   Found {result['result']['found']} apps: {result['result']['apps']}")
    else:
        print(f"   [ERROR] {result.get('error')}")

    # Test 3: list_apps
    print("\n3. Testing list_apps (with filter 'game')...")
    result = executor.execute("list_apps", {"filter_term": "game"})
    if result["success"]:
        print("   [OK] list_apps works!")
        print(f"   Found {result['result']['count']} apps with 'game' in name")
        if result['result']['apps']:
            print(f"   First few: {result['result']['apps'][:3]}")
    else:
        print(f"   [ERROR] {result.get('error')}")

    # Test 4: launch (dry run - just test the function exists)
    print("\n4. Testing launch function (NOT actually launching)...")
    # We won't actually launch anything, just verify the tool is registered
    if "launch" in executor.tools:
        print("   [OK] launch tool is registered!")
    else:
        print("   [ERROR] launch tool not found!")

    # Test 5: end_task (dry run)
    print("\n5. Testing end_task function...")
    if "end_task" in executor.tools:
        print("   [OK] end_task tool is registered!")
    else:
        print("   [ERROR] end_task tool not found!")

    # Print available tools
    print("\n" + "="*60)
    print("Available Tools:")
    print("="*60)
    for tool_name in executor.tools.keys():
        print(f"  • {tool_name}")

    print("\n" + "="*60)
    print("All tests completed!")
    print("="*60)

if __name__ == "__main__":
    test_tools()
