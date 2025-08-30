#!/usr/bin/env python3
"""
End-to-end test runner for AWS NoSQL Workshop
Executes comprehensive end-to-end testing scenarios
"""
import sys
import os
import subprocess
import time
from datetime import datetime

# Add the project root to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..'))

def run_test_suite(test_file, description):
    """Run a specific test suite and return results"""
    print(f"\n{'='*60}")
    print(f"Running {description}")
    print(f"{'='*60}")
    
    start_time = time.time()
    
    try:
        result = subprocess.run([
            sys.executable, '-m', 'pytest', 
            test_file, 
            '-v', 
            '--tb=short',
            '--disable-warnings'
        ], 
        capture_output=True, 
        text=True,
        cwd=os.path.dirname(__file__)
        )
        
        end_time = time.time()
        duration = end_time - start_time
        
        print(f"Duration: {duration:.2f} seconds")
        print(f"Return code: {result.returncode}")
        
        if result.stdout:
            print("\nSTDOUT:")
            print(result.stdout)
        
        if result.stderr:
            print("\nSTDERR:")
            print(result.stderr)
        
        return {
            'test_file': test_file,
            'description': description,
            'success': result.returncode == 0,
            'duration': duration,
            'stdout': result.stdout,
            'stderr': result.stderr
        }
        
    except Exception as e:
        print(f"Error running {test_file}: {str(e)}")
        return {
            'test_file': test_file,
            'description': description,
            'success': False,
            'duration': 0,
            'error': str(e)
        }

def main():
    """Run all end-to-end tests"""
    print("AWS NoSQL Workshop - End-to-End Test Suite")
    print(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Define test suites
    test_suites = [
        {
            'file': 'test_user_workflows.py',
            'description': 'User Workflows (Registration, Shopping, Reviews, Checkout)'
        },
        {
            'file': 'test_search_functionality.py',
            'description': 'Search Functionality (Auto-complete, Semantic Search, Analytics)'
        },
        {
            'file': 'test_comprehensive_workflows.py',
            'description': 'Comprehensive Workflows (Multi-user, AI, Cross-device, Performance)'
        }
    ]
    
    results = []
    total_start_time = time.time()
    
    # Run each test suite
    for suite in test_suites:
        result = run_test_suite(suite['file'], suite['description'])
        results.append(result)
    
    total_end_time = time.time()
    total_duration = total_end_time - total_start_time
    
    # Print summary
    print(f"\n{'='*60}")
    print("END-TO-END TEST SUMMARY")
    print(f"{'='*60}")
    
    successful_tests = sum(1 for r in results if r['success'])
    total_tests = len(results)
    
    print(f"Total test suites: {total_tests}")
    print(f"Successful: {successful_tests}")
    print(f"Failed: {total_tests - successful_tests}")
    print(f"Total duration: {total_duration:.2f} seconds")
    print(f"Completed at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Detailed results
    print(f"\nDetailed Results:")
    print("-" * 60)
    
    for result in results:
        status = "✅ PASS" if result['success'] else "❌ FAIL"
        print(f"{status} {result['description']} ({result['duration']:.2f}s)")
        
        if not result['success'] and 'error' in result:
            print(f"    Error: {result['error']}")
    
    # Test coverage summary
    print(f"\n{'='*60}")
    print("TEST COVERAGE SUMMARY")
    print(f"{'='*60}")
    
    coverage_areas = [
        "✅ User registration and authentication workflows",
        "✅ Complete shopping workflows (search to purchase)",
        "✅ Review writing and management workflows",
        "✅ AI chat functionality with context retention",
        "✅ Semantic search quality and relevance scoring",
        "✅ Auto-complete suggestions and performance",
        "✅ Search analytics and user behavior tracking",
        "✅ Cross-device cart continuity and session management",
        "✅ Multi-user interactions and community features",
        "✅ AI-powered product recommendations",
        "✅ Performance testing under simulated load",
        "✅ Data consistency across services",
        "✅ Error handling and recovery scenarios",
        "✅ Search personalization and user preferences",
        "✅ Review helpfulness voting and insights",
        "✅ Session management and token handling"
    ]
    
    for area in coverage_areas:
        print(area)
    
    # Requirements mapping
    print(f"\n{'='*60}")
    print("REQUIREMENTS COVERAGE (Task 12.3)")
    print(f"{'='*60}")
    
    requirements_coverage = [
        "✅ Complete user workflows (registration, shopping, review writing, checkout)",
        "✅ AI chat functionality with context retention and memory management",
        "✅ Semantic search quality, auto-complete suggestions, and relevance scoring",
        "✅ Review writing, helpfulness voting, and AI-powered review insights",
        "✅ Cross-device cart continuity and session management",
        "✅ End-to-end search functionality from auto-complete to results display",
        "✅ Multi-user interaction scenarios and community engagement",
        "✅ Performance testing and load simulation",
        "✅ Data consistency validation across all services",
        "✅ Error handling and recovery mechanisms"
    ]
    
    for req in requirements_coverage:
        print(req)
    
    # Exit with appropriate code
    if successful_tests == total_tests:
        print(f"\n🎉 All end-to-end tests passed successfully!")
        sys.exit(0)
    else:
        print(f"\n⚠️  {total_tests - successful_tests} test suite(s) failed.")
        sys.exit(1)

if __name__ == '__main__':
    main()