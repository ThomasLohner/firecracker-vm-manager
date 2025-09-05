# Firecracker VM Manager Test Framework

## Overview

The FCM test framework provides comprehensive testing for the Firecracker VM Manager. All tests are consolidated in a single library (`fcm_test_lib.py`) with a flexible runner (`fcm_test_runner.py`) that can execute different test subsets.

## Test Configuration

The tests use these reserved resources:
- **VM Names**: `dev-test-vm-1` through `dev-test-vm-5`
- **VM IP Range**: `10.254.254.250` - `10.254.254.254`
- **TAP IP Range**: `192.254.254.250` - `192.254.254.254`
- **Test Image**: `alpine-v1.0.ext4`
- **Test Kernel**: `vmlinux-6.1.141` (or default from config)

## Available Test Suites

| Suite | Description | Tests |
|-------|-------------|-------|
| `quick` | Basic functionality test with single VM | 1 |
| `basic` | Essential tests for core functionality | 3 |
| `network` | Network driver and TAP device tests | 3 |
| `config` | Configuration override and validation tests | 2 |
| `stress` | Stress and recovery tests | 3 |
| `full` | All available tests | 11 |
| `ci` | Optimized suite for CI/CD pipelines | 5 |

## Usage

### List Available Test Suites
```bash
python3 tests/fcm_test_runner.py --list
```

### Run a Test Suite
```bash
# Quick test (single VM lifecycle)
python3 tests/fcm_test_runner.py quick

# Full test suite (all tests)
python3 tests/fcm_test_runner.py full

# Network tests only
python3 tests/fcm_test_runner.py network

# CI/CD optimized tests
python3 tests/fcm_test_runner.py ci
```

### Run Specific Tests
```bash
# Run specific tests by name
python3 tests/fcm_test_runner.py --tests "Basic Lifecycle" "Cache Persistence"

# Run with verbose output
python3 tests/fcm_test_runner.py --tests "Config Overrides" --verbose
```

### Advanced Options
```bash
# Verbose output
python3 tests/fcm_test_runner.py full --verbose

# Skip cleanup (for debugging)
python3 tests/fcm_test_runner.py stress --no-cleanup
```

## Available Tests

### Core Tests
- **Basic Lifecycle**: VM create, stop, start, restart, destroy with full validation
- **Cache Persistence**: Tests VM configuration caching across stop/start cycles
- **List Command**: Verifies VM listing functionality

### Configuration Tests
- **Config Overrides**: Tests CPU/memory override functionality
- **MMDS Metadata**: Tests metadata injection and querying

### Network Tests
- **Internal Network Driver**: Tests automatic TAP device management
- **External Network Driver**: Tests using pre-existing TAP devices
- **TAP Allocation**: Tests TAP device allocation and reuse

### Stress Tests
- **Concurrent VMs**: Tests multiple VMs running simultaneously
- **Process Kill Recovery**: Tests recovery from killed Firecracker process
- **Error Handling**: Tests various error scenarios

## Key Features

### Comprehensive Validation
Every running VM is tested with:
- **Ping Test**: Network connectivity verification
- **API Config Query**: VM configuration via socket API
- **Cache Consistency**: Cache file matches API response
- **Config Persistence**: Settings maintained across restarts

### Safety Features
- **Taboo List**: Protects existing VMs, TAP devices, and processes
- **Reserved IPs**: Uses dedicated IP ranges for testing
- **Auto Cleanup**: Removes all test resources even on failure
- **Emergency Cleanup**: Handles interrupts (Ctrl+C) gracefully

### Configuration Support
- Reads directories from `/etc/firecracker.env`
- Adapts to custom paths for kernels, images, rootfs, sockets
- Uses defaults when configuration not available

## Test Library Structure

### fcm_test_lib.py
Single consolidated library containing:
- Setup and teardown functions
- VM management helpers
- Network and validation utilities
- API query functions
- All test implementations
- Test execution framework
- Report generation

### fcm_test_runner.py
Test runner that:
- Defines test suites
- Handles command-line arguments
- Executes selected tests
- Provides suite and custom test options
- Manages signal handlers for cleanup

## Requirements

- Python 3.6+
- Firecracker binary installed
- Supervisor daemon running
- Root/sudo access for network operations
- Test image: `alpine-v1.0.ext4` in images directory
- Test kernel: `vmlinux-6.1.141` in kernels directory (optional)

## Exit Codes

- `0`: All tests passed
- `1`: One or more tests failed

## Examples

### Quick Validation
```bash
# Quick test to validate basic functionality
python3 tests/fcm_test_runner.py quick
```

### Pre-commit Hook
```bash
# Run CI suite before committing
python3 tests/fcm_test_runner.py ci
```

### Full Regression Test
```bash
# Complete test suite with verbose output
python3 tests/fcm_test_runner.py full --verbose
```

### Debug Failed Test
```bash
# Run specific test without cleanup
python3 tests/fcm_test_runner.py --tests "Process Kill Recovery" --no-cleanup
```

## Notes

- Tests automatically clean up test VMs even if they exist from previous runs
- The framework never touches VMs or TAP devices that existed before tests started
- All test VMs are pinged to verify connectivity
- VM configurations are validated via API and compared with cache files
- Test results include timing information for performance tracking