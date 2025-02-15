import subprocess
import json
import os
from typing import Dict, Any, Optional
from datetime import datetime, timedelta

class VirtualsSDK:
    def __init__(self):
        self.current_dir = os.path.dirname(os.path.abspath(__file__))
        self.project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))

        # Update SDK path to point to sdkClient.js
        self.sdk_path = os.path.join(self.project_root, 'vp-trade-sdk', 'dist', 'vp-trade-sdk', 'sdkClient.js')

        print(f"Project root directory: {self.project_root}")
        print(f"SDK path: {self.sdk_path}")

        self._check_dependencies()
        self.last_processed_tokens = {
            'sentient': set(),
            'prototype': set()
        }
        self.last_check_time = {
            'sentient': None,
            'prototype': None
        }

    def _check_dependencies(self) -> None:
        """Check if Node.js and required packages are installed"""
        try:
            subprocess.run(['node', '--version'], capture_output=True, check=True)
        except subprocess.CalledProcessError:
            raise RuntimeError("Node.js is not installed. Please install Node.js first.")

        if not os.path.exists(self.sdk_path):
            raise RuntimeError(
                f"SDK not found at {self.sdk_path}. Please:\n"
                f"1. cd {self.project_root}\n"
                f"2. git clone https://github.com/Virtual-Protocol/vp-trade-sdk.git\n"
                f"3. cd vp-trade-sdk\n"
                f"4. npm install\n"
                f"5. npm run build"
            )

    def _execute_js(self, command: str) -> Dict[str, Any]:
        """Execute JavaScript command and return parsed results"""
        try:
            # Execute Node.js command from the project root directory
            result = subprocess.run(
                ['node', '-e', command],
                capture_output=True,
                text=True,
                check=True,
                cwd=self.project_root,
                env=os.environ
            )

            # Try to find the JSON part of the output
            output = result.stdout
            try:
                # Find the first occurrence of '{'
                json_start = output.find('{')
                if json_start >= 0:
                    json_str = output[json_start:]
                    return json.loads(json_str)
                else:
                    raise json.JSONDecodeError("No JSON found in output", output, 0)
            except json.JSONDecodeError:
                print("Full output:", output)  # Debug print
                raise Exception("Failed to parse JSON from output")

        except subprocess.CalledProcessError as e:
            print("Error output:", e.stderr)
            raise Exception(f"Error executing Node.js script: {e.stderr}")
        except Exception as e:
            raise Exception(f"Unexpected error: {str(e)}")

    def _format_token_data(self, token: Dict[str, Any], token_type: str) -> Dict[str, Any]:
        """Format token data into a standardized structure"""
        return {
            "id": str(token.get('id')),
            "name": token.get('name'),
            "symbol": token.get('symbol'),
            "token_address": token.get('tokenAddress'),
            "lp_address": token.get('lpAddress'),
            "status": token.get('status'),
            "description": token.get('description'),
            "holder_count": token.get('holderCount'),
            "market_cap": token.get('mcapInVirtual'),
            "type": token_type,
            "socials": token.get('socials', {}).get('VERIFIED_LINKS', []),
            "image_url": token.get('image', {}).get('url'),
            "network": "ethereum",  # Default to ethereum for VP Trade
            "created_at": datetime.now().isoformat(),  # Current timestamp if not provided
        }

    def _filter_new_tokens(self, tokens: list, token_type: str) -> list:
        """Filter out previously processed tokens and return only new ones"""
        current_time = datetime.now()
        new_tokens = []
        current_token_ids = set()

        for token in tokens:
            token_id = str(token.get('id'))

            # Skip if token has been processed before
            if token_id in self.last_processed_tokens[token_type]:
                continue

            # Format token data
            formatted_token = self._format_token_data(token, token_type)
            new_tokens.append(formatted_token)
            current_token_ids.add(token_id)

        # Update last processed tokens
        self.last_processed_tokens[token_type].update(current_token_ids)
        self.last_check_time[token_type] = current_time

        return new_tokens

    def get_sentient_listing(self, page_number: int = 1, page_size: int = 50) -> Dict[str, Any]:
            """Get new sentient token listings"""
            js_code = f"""
            const {{ SDKClient }} = require("{self.sdk_path}");
            require("dotenv").config();

            const config = {{
                privateKey: process.env.PRIVATE_KEY || "",
                rpcUrl: process.env.RPC_PROVIDER_URL || "",
                rpcApiKey: process.env.RPC_API_KEY || "",
                virtualApiUrl: process.env.VIRTUALS_API_URL || "",
                virtualApiUrlV2: process.env.VIRTUALS_API_URL_V2 || "",
            }};

            const sdkClient = new SDKClient(config);

            (async () => {{
                try {{
                    const result = await sdkClient.getSentientListing({page_number}, {page_size});
                    console.log(JSON.stringify(result));
                }} catch (error) {{
                    console.error(JSON.stringify({{ error: error.message }}));
                    process.exit(1);
                }}
            }})();
            """
            result = self._execute_js(js_code)
            if 'tokens' in result:
                result['tokens'] = self._filter_new_tokens(result['tokens'], 'sentient')
            return result

    def get_prototype_listing(self, page_number: int = 1, page_size: int = 50) -> Dict[str, Any]:
        """Get new prototype token listings"""
        js_code = f"""
        const {{ SDKClient }} = require("{self.sdk_path}");
        require("dotenv").config();

        const config = {{
            privateKey: process.env.PRIVATE_KEY || "",
            rpcUrl: process.env.RPC_PROVIDER_URL || "",
            rpcApiKey: process.env.RPC_API_KEY || "",
            virtualApiUrl: process.env.VIRTUALS_API_URL || "",
            virtualApiUrlV2: process.env.VIRTUALS_API_URL_V2 || "",
        }};

        const sdkClient = new SDKClient(config);

        (async () => {{
            try {{
                const result = await sdkClient.getPrototypeListing({page_number}, {page_size});
                console.log(JSON.stringify(result));
            }} catch (error) {{
                console.error(JSON.stringify({{ error: error.message }}));
                process.exit(1);
            }}
        }})();
        """
        result = self._execute_js(js_code)
        if 'tokens' in result:
            result['tokens'] = self._filter_new_tokens(result['tokens'], 'prototype')
        return result
