#!/usr/bin/env python3
import os
import sys

def check_openai():
    try:
        import openai
        print("✅ OpenAI library imported")
        
        # Check API key
        api_key = os.getenv('OPENAI_API_KEY')
        if api_key:
            print(f"✅ API key found (length: {len(api_key)})")
            if api_key.startswith('sk-'):
                print("✅ API key format looks correct")
            else:
                print("⚠️ API key doesn't start with 'sk-'")
        else:
            print("❌ No OPENAI_API_KEY found")
            
        return True
    except ImportError as e:
        print(f"❌ OpenAI import failed: {e}")
        return False

def check_rust():
    import subprocess
    try:
        result = subprocess.run(['cargo', '--version'], capture_output=True, text=True)
        if result.returncode == 0:
            print(f"✅ Cargo found: {result.stdout.strip()}")
            return True
        else:
            print("❌ Cargo not working")
            return False
    except FileNotFoundError:
        print("❌ Cargo not found - Rust toolchain not installed")
        return False

def test_simple_openai_call():
    try:
        import openai
        
        # Test the API call
        client = openai.OpenAI()  # Uses newer client
        
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": "Say 'Hello World' in Rust"}],
            max_tokens=50
        )
        
        print("✅ OpenAI API call successful!")
        print(f"Response: {response.choices[0].message.content}")
        return True
        
    except Exception as e:
        print(f"❌ OpenAI API call failed: {e}")
        return False

if __name__ == "__main__":
    print("🔍 Diagnostic Check")
    print("=" * 30)
    
    openai_ok = check_openai()
    rust_ok = check_rust()
    
    if openai_ok:
        api_ok = test_simple_openai_call()
    else:
        api_ok = False
    
    print("\n📊 Summary:")
    print(f"OpenAI Library: {'✅' if openai_ok else '❌'}")
    print(f"Rust/Cargo: {'✅' if rust_ok else '❌'}")
    print(f"API Calls: {'✅' if api_ok else '❌'}")
    
    if not rust_ok:
        print("\n🛠️ To install Rust:")
        print("Visit: https://rustup.rs/")
        print("Or run: curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh")
