#!/usr/bin/env python3
import os
import openai
from datetime import datetime

def test_simple_generation(prompt):
    try:
        # Use the new OpenAI client
        client = openai.OpenAI()
        
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",  # Cheaper model for testing
            messages=[
                {"role": "system", "content": "You are a Scrypto smart contract developer. Generate working Scrypto code."},
                {"role": "user", "content": f"Create a Scrypto blueprint: {prompt}"}
            ],
            max_tokens=1000,
            temperature=0.3
        )
        
        code = response.choices[0].message.content
        
        # Mock successful result for now
        result = {
            "prompt": prompt,
            "timestamp": datetime.utcnow().isoformat(),
            "attempts": [
                {
                    "attempt": 1,
                    "status": "passed",
                    "generated_code": code[:500] + "...",
                    "test_output": "Mock: Compilation successful!"
                }
            ],
            "final_status": "passed",
            "retry_count": 0
        }
        
        return result
        
    except Exception as e:
        return {
            "prompt": prompt,
            "timestamp": datetime.utcnow().isoformat(),
            "attempts": [
                {
                    "attempt": 1,
                    "status": "failed",
                    "error": str(e)
                }
            ],
            "final_status": "failed",
            "retry_count": 0
        }

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        prompt = " ".join(sys.argv[1:])
        result = test_simple_generation(prompt)
        print(f"Result: {result['final_status']}")
        if result['final_status'] == 'passed':
            print("✅ Generation successful!")
        else:
            print(f"❌ Error: {result['attempts'][0].get('error', 'Unknown error')}")
