#!/usr/bin/env python3
"""
Test script to verify the OCR bbox matcher fix.

This tests the exact scenario from the debug log where 'Dr. P.N. Cundall,' 
was not matching because of tokenization mismatch.
"""

import sys
import json

# Add backend to path
sys.path.insert(0, 'backend')

from app.services.bbox_matcher import BBoxMatcher


def test_dr_cundall_match():
    """Test the exact case from the debug log."""
    
    # The quote that was failing
    quote_text = "Dr. P.N. Cundall,"
    
    # Simulated document structure (simplified from debug log)
    document_bboxes = {
        'pages': [{
            'page_number': 1,
            'lines': [{
                'line_text': 'Dr. P.N. Cundall,',
                'words': [
                    {'text': 'Dr.', 'bbox': [0.164, 0.298, 0.197, 0.314], 'confidence': 0.999},
                    {'text': 'P.N.', 'bbox': [0.203, 0.298, 0.244, 0.313], 'confidence': 0.999},
                    {'text': 'Cundall,', 'bbox': [0.253, 0.298, 0.331, 0.313], 'confidence': 0.996}
                ]
            }]
        }]
    }
    
    # Create matcher and test
    matcher = BBoxMatcher()
    
    print("=" * 60)
    print("TEST: OCR Quote Matching Fix")
    print("=" * 60)
    print(f"\nQuote to match: '{quote_text}'")
    print(f"\nDocument words: {[w['text'] for w in document_bboxes['pages'][0]['lines'][0]['words']]}")
    
    # Test normalization pipeline
    quote_tokens = matcher._normalize_and_tokenize(quote_text)
    print(f"\nQuote tokens after normalization: {quote_tokens}")
    print(f"Number of tokens: {len(quote_tokens)}")
    
    # Build document tokens using new approach
    pages = document_bboxes['pages']
    all_word_data, doc_tokens, token_to_word = matcher._build_doc_tokens(pages)
    
    print(f"\nDocument tokens after normalization: {doc_tokens}")
    print(f"Number of tokens: {len(doc_tokens)}")
    print(f"Token to word mapping: {token_to_word}")
    
    # Now test the actual matching
    result = matcher.match_quote_to_words(quote_text, document_bboxes, page_number=1)
    
    print("\n" + "=" * 60)
    print("MATCHING RESULT:")
    print("=" * 60)
    
    if result:
        print(f"✅ SUCCESS! Found {len(result)} matching word spans:")
        for i, span in enumerate(result, 1):
            print(f"  {i}. '{span['text']}' - bbox: {span['bbox']}")
        
        # Verify we got all 3 words
        matched_texts = [span['text'] for span in result]
        expected_texts = ['Dr.', 'P.N.', 'Cundall,']
        
        if matched_texts == expected_texts:
            print("\n✅ PERFECT! All words matched correctly in the right order!")
            return True
        else:
            print(f"\n⚠️  WARNING: Matched words {matched_texts} don't match expected {expected_texts}")
            return False
    else:
        print("❌ FAILED! No match found.")
        print("\nThis means the tokenization mismatch bug is still present.")
        return False


def test_edge_cases():
    """Test additional edge cases."""
    print("\n\n" + "=" * 60)
    print("EDGE CASE TESTS")
    print("=" * 60)
    
    matcher = BBoxMatcher()
    
    test_cases = [
        {
            'name': 'Simple word',
            'quote': 'Hello',
            'doc': {
                'pages': [{
                    'page_number': 1,
                    'lines': [{
                        'words': [{'text': 'Hello', 'bbox': [0, 0, 1, 1], 'confidence': 1.0}]
                    }]
                }]
            },
            'expected': 1
        },
        {
            'name': 'Multiple punctuation',
            'quote': 'U.S.A.',
            'doc': {
                'pages': [{
                    'page_number': 1,
                    'lines': [{
                        'words': [{'text': 'U.S.A.', 'bbox': [0, 0, 1, 1], 'confidence': 1.0}]
                    }]
                }]
            },
            'expected': 1
        },
        {
            'name': 'Word with trailing comma',
            'quote': 'world,',
            'doc': {
                'pages': [{
                    'page_number': 1,
                    'lines': [{
                        'words': [{'text': 'world,', 'bbox': [0, 0, 1, 1], 'confidence': 1.0}]
                    }]
                }]
            },
            'expected': 1
        }
    ]
    
    all_passed = True
    for test in test_cases:
        result = matcher.match_quote_to_words(test['quote'], test['doc'])
        passed = len(result) == test['expected']
        status = "✅" if passed else "❌"
        print(f"\n{status} {test['name']}: '{test['quote']}'")
        if not passed:
            print(f"   Expected {test['expected']} matches, got {len(result)}")
            all_passed = False
    
    return all_passed


if __name__ == '__main__':
    print("\nTesting OCR BBox Matcher Fix...\n")
    
    # Run main test
    main_test_passed = test_dr_cundall_match()
    
    # Run edge cases
    edge_cases_passed = test_edge_cases()
    
    # Final result
    print("\n\n" + "=" * 60)
    print("FINAL RESULTS")
    print("=" * 60)
    
    if main_test_passed and edge_cases_passed:
        print("\n🎉 ALL TESTS PASSED! The fix is working correctly.")
        sys.exit(0)
    else:
        print("\n❌ SOME TESTS FAILED. Please review the implementation.")
        sys.exit(1)
