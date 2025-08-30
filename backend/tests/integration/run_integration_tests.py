#!/usr/bin/env python3
"""
Integration test runner for database operations
Runs integration tests with proper setup and teardown
"""
import sys
import os
import subprocess
import argparse
import time

def check_dependencies():
    """Check if required services are available"""
    services_status = {
        'mongodb': False,
        'redis': False
    }
    
    # Check MongoDB
    try:
        import pymongo
        client = pymongo.MongoClient('mongodb://localhost:27017/', serverSelectionTimeoutMS=1000)
        client.server_info()
        services_status['mongodb'] = True
        client.close()
        print("✅ MongoDB connection successful")
    except Exception as e:
        print(f"⚠️  MongoDB not available: {e}")
        print("   Integration tests will use mocked MongoDB")
    
    # Check Redis
    try:
        import redis
        r = redis.Redis(host='localhost', port=6379, db=1)
        r.ping()
        services_status['redis'] = True
        print("✅ Redis connection successful")
    except Exception as e:
        print(f"⚠️  Redis not available: {e}")
        print("   Integration tests will use FakeRedis")
    
    return services_status

def run_integration_tests(test_file=None, coverage=True, verbose=False, services=None):
    """Run integration tests with optional coverage reporting"""
    
    # Set up test environment
    test_dir = os.path.dirname(os.path.abspath(__file__))
    backend_dir = os.path.dirname(os.path.dirname(test_dir))
    
    # Add backend directories to Python path
    sys.path.insert(0, os.path.join(backend_dir, 'functions'))
    sys.path.insert(0, os.path.join(backend_dir, 'shared'))
    
    # Check service dependencies
    print("Checking service dependencies...")
    services_status = check_dependencies()
    
    # Build pytest command
    cmd = ['python', '-m', 'pytest']
    
    if test_file:
        cmd.append(test_file)
    else:
        cmd.append(test_dir)
    
    if coverage:
        cmd.extend([
            '--cov=functions',
            '--cov=shared',
            '--cov-report=html:integration_coverage_html',
            '--cov-report=term-missing',
            '--cov-fail-under=70'  # Lower threshold for integration tests
        ])
    
    if verbose:
        cmd.append('-v')
    
    # Add other useful options
    cmd.extend([
        '--tb=short',
        '--strict-markers',
        '-x',  # Stop on first failure
        '--durations=10'  # Show 10 slowest tests
    ])
    
    # Set environment variables for tests
    env = os.environ.copy()
    env['PYTEST_CURRENT_TEST'] = 'integration'
    
    print(f"\nRunning command: {' '.join(cmd)}")
    print(f"Working directory: {backend_dir}")
    print(f"Services available: {services_status}")
    
    # Run tests
    try:
        start_time = time.time()
        result = subprocess.run(cmd, cwd=backend_dir, env=env, check=False)
        end_time = time.time()
        
        print(f"\nTest execution time: {end_time - start_time:.2f} seconds")
        return result.returncode
    except Exception as e:
        print(f"Error running integration tests: {e}")
        return 1

def setup_test_environment():
    """Set up test environment and dependencies"""
    print("Setting up test environment...")
    
    # Install test requirements if needed
    requirements_file = os.path.join(os.path.dirname(__file__), 'test_requirements.txt')
    if os.path.exists(requirements_file):
        try:
            subprocess.run([
                'pip', 'install', '-r', requirements_file
            ], check=True, capture_output=True)
            print("✅ Test requirements installed")
        except subprocess.CalledProcessError as e:
            print(f"⚠️  Failed to install test requirements: {e}")
    
    return True

def main():
    """Main function"""
    parser = argparse.ArgumentParser(description='Run integration tests for database operations')
    parser.add_argument('--test-file', '-f', help='Specific test file to run')
    parser.add_argument('--no-coverage', action='store_true', help='Skip coverage reporting')
    parser.add_argument('--verbose', '-v', action='store_true', help='Verbose output')
    parser.add_argument('--setup', action='store_true', help='Set up test environment')
    parser.add_argument('--check-services', action='store_true', help='Only check service availability')
    
    args = parser.parse_args()
    
    if args.setup:
        setup_success = setup_test_environment()
        if not setup_success:
            print("❌ Test environment setup failed")
            sys.exit(1)
        print("✅ Test environment setup complete")
        return
    
    if args.check_services:
        services_status = check_dependencies()
        print(f"\nService Status Summary:")
        for service, status in services_status.items():
            status_icon = "✅" if status else "❌"
            print(f"  {status_icon} {service}: {'Available' if status else 'Not Available'}")
        return
    
    return_code = run_integration_tests(
        test_file=args.test_file,
        coverage=not args.no_coverage,
        verbose=args.verbose
    )
    
    if return_code == 0:
        print("\n✅ All integration tests passed!")
        if not args.no_coverage:
            print("📊 Coverage report generated in integration_coverage_html/index.html")
    else:
        print(f"\n❌ Integration tests failed with return code: {return_code}")
    
    sys.exit(return_code)

if __name__ == '__main__':
    main()