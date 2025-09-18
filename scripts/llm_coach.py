#!/usr/bin/env python3
"""
LLM Coach Script for Scrypto Code Generation

This script handles the prompt-to-code pipeline:
1. Send prompt to ChatGPT/OpenAI API
2. Extract Scrypto code from response
3. Write .rs file to output/
4. Run cargo scrypto test
5. Handle retry on compilation errors
"""

import os
import re
import json
import subprocess
import sys
from datetime import datetime
from typing import Dict, List, Optional, Tuple
import openai
from pathlib import Path

class ScryptoLLMCoach:
    def __init__(self, api_key: Optional[str] = None):
        """Initialize the LLM coach with OpenAI API."""
        self.api_key = api_key or os.getenv('OPENAI_API_KEY')
        if not self.api_key:
            raise ValueError("OpenAI API key required. Set OPENAI_API_KEY env var.")
        
        openai.api_key = self.api_key
        self.output_dir = Path("output")
        self.output_dir.mkdir(exist_ok=True)
        
        # Load knowledge base for context
        self.kb_context = self._load_knowledge_base()
        
    def _load_knowledge_base(self) -> str:
        """Load cleaned documentation for prompt context."""
        kb_dir = Path("kb/cleaned")
        if not kb_dir.exists():
            return ""
        
        context_parts = []
        for file_path in kb_dir.glob("*.md"):
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()[:2000]  # Limit context size
                    context_parts.append(f"=== {file_path.name} ===\n{content}\n")
            except Exception as e:
                print(f"Warning: Could not load {file_path}: {e}")
        
        return "\n".join(context_parts[:5])  # Limit to 5 examples
    
    def _build_prompt(self, user_request: str, error_context: Optional[str] = None) -> str:
        """Build the complete prompt with context and instructions."""
        
        base_prompt = f"""You are a Scrypto (RadixDLT smart contract) code generator.

CONTEXT - Key Scrypto Patterns:
{self.kb_context[:1500]}

INSTRUCTIONS:
1. Generate COMPLETE, COMPILABLE Scrypto code
2. Include ALL necessary imports
3. Use proper Scrypto v1.0+ syntax  
4. Include basic tests
5. Follow asset-oriented programming patterns
6. Return ONLY the Rust/Scrypto code, no explanations

USER REQUEST: {user_request}
"""

        if error_context:
            base_prompt += f"""

PREVIOUS COMPILATION ERROR:
{error_context}

Please fix the above error and provide corrected code.
"""

        return base_prompt
    
    def _extract_scrypto_code(self, response_text: str) -> Optional[str]:
        """Extract Scrypto code from LLM response."""
        
        # Try to find code in markdown blocks
        code_patterns = [
            r'```rust\n(.*?)\n```',
            r'```scrypto\n(.*?)\n```', 
            r'```\n(.*?)\n```',
            r'```rust(.*?)```',
            r'```(.*?)```'
        ]
        
        for pattern in code_patterns:
            matches = re.findall(pattern, response_text, re.DOTALL)
            if matches:
                code = matches[0].strip()
                if self._looks_like_scrypto(code):
                    return code
        
        # If no code blocks found, check if entire response is code
        if self._looks_like_scrypto(response_text):
            return response_text.strip()
            
        return None
    
    def _looks_like_scrypto(self, code: str) -> bool:
        """Check if text looks like Scrypto code."""
        scrypto_indicators = [
            'use scrypto::prelude::*',
            '#[blueprint]',
            'impl',
            'ResourceAddress',
            'ComponentAddress',
            'Bucket',
            'Vault'
        ]
        
        return any(indicator in code for indicator in scrypto_indicators)
    
    def _write_code_file(self, code: str, blueprint_name: str) -> Path:
        """Write generated code to output directory."""
        
        # Create package structure
        package_dir = self.output_dir / blueprint_name
        package_dir.mkdir(exist_ok=True)
        
        src_dir = package_dir / "src"
        src_dir.mkdir(exist_ok=True)
        
        # Write Cargo.toml
        cargo_toml = f'''[package]
name = "{blueprint_name}"
version = "0.1.0"
edition = "2021"

[dependencies]
scrypto = {{ git = "https://github.com/radixdlt/radixdlt-scrypto", tag = "v1.0.1" }}

[dev-dependencies]
scrypto-unit = {{ git = "https://github.com/radixdlt/radixdlt-scrypto", tag = "v1.0.1" }}
transaction = {{ git = "https://github.com/radixdlt/radixdlt-scrypto", tag = "v1.0.1" }}

[[bin]]
name = "main"
'''
        
        (package_dir / "Cargo.toml").write_text(cargo_toml)
        
        # Write main code file
        code_file = src_dir / "lib.rs"
        code_file.write_text(code)
        
        return code_file
    
    def _run_tests(self, package_dir: Path) -> Tuple[bool, str, str]:
        """Run cargo scrypto test and return results."""
        
        try:
            # First try to compile
            compile_result = subprocess.run(
                ["cargo", "check"],
                cwd=package_dir,
                capture_output=True,
                text=True,
                timeout=60
            )
            
            if compile_result.returncode != 0:
                return False, compile_result.stderr, "compilation_error"
            
            # Then run tests
            test_result = subprocess.run(
                ["cargo", "test"],
                cwd=package_dir,
                capture_output=True,
                text=True,
                timeout=120
            )
            
            success = test_result.returncode == 0
            output = test_result.stdout + test_result.stderr
            
            return success, output, "test_complete"
            
        except subprocess.TimeoutExpired:
            return False, "Test execution timed out", "timeout"
        except FileNotFoundError:
            return False, "cargo command not found", "missing_cargo"
        except Exception as e:
            return False, f"Test execution failed: {str(e)}", "execution_error"
    
    def generate_and_test(self, prompt: str, max_retries: int = 1) -> Dict:
        """Main method: generate code from prompt and test it."""
        
        result = {
            "prompt": prompt,
            "timestamp": datetime.utcnow().isoformat(),
            "attempts": [],
            "final_status": "failed",
            "retry_count": 0
        }
        
        error_context = None
        
        for attempt in range(max_retries + 1):
            print(f"\nAttempt {attempt + 1} for prompt: {prompt[:50]}...")
            
            # Generate code
            try:
                full_prompt = self._build_prompt(prompt, error_context)
                
                response = openai.ChatCompletion.create(
                    model="gpt-4",
                    messages=[{"role": "user", "content": full_prompt}],
                    max_tokens=2000,
                    temperature=0.3
                )
                
                response_text = response.choices[0].message.content
                code = self._extract_scrypto_code(response_text)
                
                if not code:
                    result["attempts"].append({
                        "attempt": attempt + 1,
                        "status": "failed",
                        "error": "Could not extract valid Scrypto code",
                        "response_preview": response_text[:200]
                    })
                    continue
                
            except Exception as e:
                result["attempts"].append({
                    "attempt": attempt + 1,
                    "status": "failed",
                    "error": f"LLM API error: {str(e)}"
                })
                continue
            
            # Write and test code
            blueprint_name = f"generated_{hash(prompt) % 10000}"
            
            try:
                code_file = self._write_code_file(code, blueprint_name)
                package_dir = code_file.parent.parent
                
                success, test_output, test_type = self._run_tests(package_dir)
                
                attempt_result = {
                    "attempt": attempt + 1,
                    "status": "passed" if success else "failed",
                    "code_file": str(code_file.relative_to(Path.cwd())),
                    "test_output": test_output,
                    "test_type": test_type
                }
                
                result["attempts"].append(attempt_result)
                
                if success:
                    result["final_status"] = "passed"
                    result["retry_count"] = attempt
                    print(f"✅ Success on attempt {attempt + 1}")
                    break
                else:
                    print(f"❌ Failed attempt {attempt + 1}: {test_type}")
                    # Prepare error context for retry
                    if attempt < max_retries:
                        error_context = test_output[-1000:]  # Last 1000 chars
                        result["retry_count"] = attempt + 1
                    
            except Exception as e:
                result["attempts"].append({
                    "attempt": attempt + 1,
                    "status": "failed",
                    "error": f"Code generation error: {str(e)}"
                })
        
        return result
    
    def batch_generate(self, prompts: List[str]) -> List[Dict]:
        """Generate and test multiple prompts."""
        results = []
        
        for i, prompt in enumerate(prompts):
            print(f"\n{'='*60}")
            print(f"Processing {i+1}/{len(prompts)}: {prompt}")
            print('='*60)
            
            result = self.generate_and_test(prompt)
            results.append(result)
            
            # Save intermediate results
            self._save_results(results)
        
        return results
    
    def _save_results(self, results: List[Dict]):
        """Save results to JSON file."""
        
        summary = {
            "total_attempts": len(results),
            "successful": sum(1 for r in results if r["final_status"] == "passed"),
            "failed": sum(1 for r in results if r["final_status"] == "failed"),
            "retry_rate": sum(r["retry_count"] for r in results) / len(results) if results else 0
        }
        
        output_data = {
            "timestamp": datetime.utcnow().isoformat(),
            "results": results,
            "summary": summary
        }
        
        with open("results.json", "w") as f:
            json.dump(output_data, f, indent=2)
        
        print(f"\n📊 Results saved: {summary['successful']}/{summary['total_attempts']} successful")

def main():
    """Command line interface."""
    
    if len(sys.argv) < 2:
        print("Usage: python llm_coach.py 'Your Scrypto prompt here'")
        print("       python llm_coach.py --batch  # Run predefined test prompts")
        return
    
    coach = ScryptoLLMCoach()
    
    if sys.argv[1] == "--batch":
        # Predefined test prompts
        test_prompts = [
            "Create a trivial hello world blueprint that gives out tokens",
            "Create an admin-controlled NFT blueprint with minting permissions",
            "Create a simple token faucet that distributes tokens with rate limiting",
            "Create a basic DEX blueprint for token swapping"
        ]
        
        results = coach.batch_generate(test_prompts)
        
        print(f"\n🎯 Batch complete: {len([r for r in results if r['final_status'] == 'passed'])} successful")
        
    else:
        # Single prompt
        prompt = " ".join(sys.argv[1:])
        result = coach.generate_and_test(prompt)
        
        if result["final_status"] == "passed":
            print(f"\n✅ SUCCESS: Generated working Scrypto blueprint")
            print(f"Retries needed: {result['retry_count']}")
        else:
            print(f"\n❌ FAILED: Could not generate working code")
        
        # Save single result
        coach._save_results([result])

if __name__ == "__main__":
    main()