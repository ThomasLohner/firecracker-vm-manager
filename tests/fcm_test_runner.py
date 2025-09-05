#!/usr/bin/env python3
"""
Firecracker VM Manager Test Runner
Executes different subsets of tests from the test library
"""

import sys
import signal
import argparse
from datetime import datetime
from fcm_test_lib import FCMTestLibrary


# Define test suites
TEST_SUITES = {
    'quick': {
        'name': 'Quick Test Suite',
        'description': 'Basic functionality test with single VM',
        'tests': [
            ('Basic Lifecycle', 'test_basic_lifecycle'),
        ]
    },
    'basic': {
        'name': 'Basic Test Suite',
        'description': 'Essential tests for core functionality',
        'tests': [
            ('Basic Lifecycle', 'test_basic_lifecycle'),
            ('Cache Persistence', 'test_cache_persistence'),
            ('List Command', 'test_list_command'),
        ]
    },
    'network': {
        'name': 'Network Test Suite',
        'description': 'Network driver and TAP device tests',
        'tests': [
            ('Internal Network Driver', 'test_internal_driver'),
            ('External Network Driver', 'test_external_driver'),
            ('TAP Allocation', 'test_tap_allocation'),
        ]
    },
    'config': {
        'name': 'Configuration Test Suite',
        'description': 'Configuration override and validation tests',
        'tests': [
            ('Config Overrides', 'test_config_overrides'),
            ('MMDS Metadata', 'test_mmds'),
        ]
    },
    'stress': {
        'name': 'Stress Test Suite',
        'description': 'Stress and recovery tests',
        'tests': [
            ('Concurrent VMs', 'test_concurrent_vms'),
            ('Process Kill Recovery', 'test_kill_recovery'),
            ('Error Handling', 'test_error_handling'),
        ]
    },
    'full': {
        'name': 'Full Test Suite',
        'description': 'All available tests',
        'tests': [
            ('Basic Lifecycle', 'test_basic_lifecycle'),
            ('Config Overrides', 'test_config_overrides'),
            ('Concurrent VMs', 'test_concurrent_vms'),
            ('Internal Network Driver', 'test_internal_driver'),
            ('External Network Driver', 'test_external_driver'),
            ('Process Kill Recovery', 'test_kill_recovery'),
            ('MMDS Metadata', 'test_mmds'),
            ('Cache Persistence', 'test_cache_persistence'),
            ('TAP Allocation', 'test_tap_allocation'),
            ('Error Handling', 'test_error_handling'),
            ('List Command', 'test_list_command'),
        ]
    },
    'ci': {
        'name': 'CI/CD Test Suite',
        'description': 'Optimized suite for CI/CD pipelines',
        'tests': [
            ('Basic Lifecycle', 'test_basic_lifecycle'),
            ('Config Overrides', 'test_config_overrides'),
            ('Cache Persistence', 'test_cache_persistence'),
            ('Internal Network Driver', 'test_internal_driver'),
            ('Error Handling', 'test_error_handling'),
        ]
    }
}


def print_available_suites():
    """Print all available test suites"""
    print("\n📦 Available Test Suites:")
    print("=" * 60)
    for suite_name, suite_info in TEST_SUITES.items():
        print(f"\n{suite_name:12} - {suite_info['name']}")
        print(f"              {suite_info['description']}")
        print(f"              Tests: {len(suite_info['tests'])}")
        test_names = [test[0] for test in suite_info['tests']]
        print(f"              • {', '.join(test_names[:3])}", end="")
        if len(test_names) > 3:
            print(f" + {len(test_names) - 3} more")
        else:
            print()


def run_suite(suite_name, verbose=False, no_cleanup=False):
    """Run a specific test suite"""
    if suite_name not in TEST_SUITES:
        print(f"❌ Unknown test suite: {suite_name}")
        print_available_suites()
        return 1
    
    suite = TEST_SUITES[suite_name]
    
    print(f"\n🚀 {suite['name']}")
    print("=" * 60)
    print(f"Description: {suite['description']}")
    print(f"Tests to run: {len(suite['tests'])}")
    print(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    
    # Initialize test framework
    framework = FCMTestLibrary()
    framework.verbose = verbose
    
    # Set up signal handler for cleanup
    def signal_handler(_signum, _frame):
        print("\n\n⚠️  Interrupted! Running cleanup...")
        if not no_cleanup:
            framework.teardown()
        sys.exit(1)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    success = False
    try:
        # Setup
        framework.setup()
        
        # Run tests
        for test_name, test_method in suite['tests']:
            if hasattr(framework, test_method):
                test_func = getattr(framework, test_method)
                framework.run_test(test_name, test_func)
            else:
                print(f"⚠️  Test method not found: {test_method}")
        
        # Generate report
        success = framework.generate_report()
        
    except Exception as e:
        print(f"\n❌ Test framework error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # Always run teardown unless explicitly disabled
        if not no_cleanup:
            framework.teardown()
    
    print(f"\nFinished at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    
    return 0 if success else 1


def run_custom_tests(test_names, verbose=False, no_cleanup=False):
    """Run specific tests by name"""
    # Build a mapping of all available tests
    all_tests = {}
    for suite_info in TEST_SUITES.values():
        for test_name, test_method in suite_info['tests']:
            if test_name not in all_tests:
                all_tests[test_name] = test_method
    
    # Validate requested tests
    tests_to_run = []
    for test_name in test_names:
        if test_name in all_tests:
            tests_to_run.append((test_name, all_tests[test_name]))
        else:
            print(f"⚠️  Unknown test: {test_name}")
            print(f"Available tests: {', '.join(sorted(all_tests.keys()))}")
            return 1
    
    if not tests_to_run:
        print("❌ No valid tests specified")
        return 1
    
    print(f"\n🚀 Custom Test Run")
    print("=" * 60)
    print(f"Tests to run: {len(tests_to_run)}")
    print(f"Tests: {', '.join([t[0] for t in tests_to_run])}")
    print(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    
    # Initialize test framework
    framework = FCMTestLibrary()
    framework.verbose = verbose
    
    # Set up signal handler
    def signal_handler(_signum, _frame):
        print("\n\n⚠️  Interrupted! Running cleanup...")
        if not no_cleanup:
            framework.teardown()
        sys.exit(1)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    success = False
    try:
        # Setup
        framework.setup()
        
        # Run tests
        for test_name, test_method in tests_to_run:
            if hasattr(framework, test_method):
                test_func = getattr(framework, test_method)
                framework.run_test(test_name, test_func)
            else:
                print(f"⚠️  Test method not found: {test_method}")
        
        # Generate report
        success = framework.generate_report()
        
    except Exception as e:
        print(f"\n❌ Test framework error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        if not no_cleanup:
            framework.teardown()
    
    print(f"\nFinished at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    
    return 0 if success else 1


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description='Firecracker VM Manager Test Runner',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s quick              # Run quick test suite
  %(prog)s full               # Run all tests
  %(prog)s network            # Run network tests
  %(prog)s ci                 # Run CI/CD optimized tests
  %(prog)s --list             # Show available test suites
  %(prog)s --tests "Basic Lifecycle" "Cache Persistence"  # Run specific tests
  %(prog)s full --verbose     # Run with verbose output
  %(prog)s stress --no-cleanup  # Skip cleanup (for debugging)
        """
    )
    
    parser.add_argument(
        'suite',
        nargs='?',
        choices=list(TEST_SUITES.keys()),
        help='Test suite to run'
    )
    
    parser.add_argument(
        '--list',
        action='store_true',
        help='List available test suites'
    )
    
    parser.add_argument(
        '--tests',
        nargs='+',
        metavar='TEST',
        help='Run specific tests by name'
    )
    
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Enable verbose output'
    )
    
    parser.add_argument(
        '--no-cleanup',
        action='store_true',
        help='Skip cleanup (useful for debugging)'
    )
    
    args = parser.parse_args()
    
    # Handle --list
    if args.list:
        print_available_suites()
        return 0
    
    # Handle custom tests
    if args.tests:
        return run_custom_tests(args.tests, args.verbose, args.no_cleanup)
    
    # Handle suite
    if args.suite:
        return run_suite(args.suite, args.verbose, args.no_cleanup)
    
    # No action specified
    print("❌ No test suite specified")
    print_available_suites()
    print("\nUsage: fcm_test_runner.py [suite_name]")
    print("       fcm_test_runner.py --tests [test_names...]")
    print("       fcm_test_runner.py --list")
    return 1


if __name__ == '__main__':
    sys.exit(main())