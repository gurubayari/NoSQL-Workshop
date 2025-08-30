#!/usr/bin/env python3
"""
Test runner for Lambda function unit tests
Runs all unit tests with coverage reporting
"""
import sys
import os
import subprocess
import argparse

def run_tests(test_file=None, coverage=True, verbose=False):
    """Run unit tests with optional coverage reporting"""
    
    # Set up test environment
    test_dir = os.path.dirname(os.path.abspath(__file__))
    backend_dir = os.path.dirname(os.path.dirname(test_dir))
    
    # Add backend directories to Python path
    sys.path.insert(0, os.path.join(backend_dir, 'functions'))
    sys.path.insert(0, os.path.join(backend_dir, 'shared'))
    
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
            '--cov-report=html:coverage_html',
            '--cov-report=term-missing',
            '--cov-fail-under=80'
        ])
    
    if verbose:
        cmd.append('-v')
    
    # Add other useful options
    cmd.extend([
        '--tb=short',
        '--strict-markers',
        '-x'  # Stop on first failure
    ])
    
    print(f"Running command: {' '.join(cmd)}")
    print(f"Working directory: {os.getcwd()}")
    
    # Run tests
    try:
        result = subprocess.run(cmd, cwd=backend_dir, check=False)
        return result.returncode
    except Exception as e:
        print(f"Error running tests: {e}")
        return 1

def main():
    """Main function"""
    parser = argparse.ArgumentParser(description='Run Lambda function unit tests')
    parser.add_argument('--test-file', '-f', help='Specific test file to run')
    parser.add_argument('--no-coverage', action='store_true', help='Skip coverage reporting')
    parser.add_argument('--verbose', '-v', action='store_true', help='Verbose output')
    
    args = parser.parse_args()
    
    return_code = run_tests(
        test_file=args.test_file,
        coverage=not args.no_coverage,
        verbose=args.verbose
    )
    
    if return_code == 0:
        print("\n✅ All tests passed!")
        if not args.no_coverage:
            print("📊 Coverage report generated in coverage_html/index.html")
    else:
        print(f"\n❌ Tests failed with return code: {return_code}")
    
    sys.exit(return_code)

if __name__ == '__main__':
    main()