import asyncio
import json
import base64
import os
from datetime import datetime
from playwright.async_api import async_playwright

async def make_api_request(page, prompt="A detailed oil painting of purple clouds"):
    """
    Makes the API request to the inference endpoint with a customizable prompt
    """
    try:
        # Wait a bit for the page to fully settle
        await asyncio.sleep(3)
        
        # Prepare the request payload
        payload = {
            "model": "@cf/bytedance/stable-diffusion-xl-lightning",
            "prompt": prompt,
            "num_steps": 4,
            "guidance": 1
        }
        
        print(f"Making API request with prompt: '{prompt}'")
        
        # Use page.evaluate to make the request from within the browser context
        # This bypasses Cloudflare's bot detection
        result = await page.evaluate("""
            async (payload) => {
                try {
                    const response = await fetch('/api/inference', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                            'Accept': '*/*'
                        },
                        body: JSON.stringify(payload)
                    });
                    
                    const contentType = response.headers.get('content-type');
                    
                    if (contentType && contentType.includes('image')) {
                        // Handle image response - use more efficient base64 conversion
                        const arrayBuffer = await response.arrayBuffer();
                        const uint8Array = new Uint8Array(arrayBuffer);
                        
                        // Convert to base64 in chunks to avoid stack overflow
                        let binary = '';
                        const chunkSize = 8192;
                        for (let i = 0; i < uint8Array.length; i += chunkSize) {
                            const chunk = uint8Array.slice(i, i + chunkSize);
                            binary += String.fromCharCode.apply(null, chunk);
                        }
                        const base64String = btoa(binary);
                        
                        return {
                            status: response.status,
                            ok: response.ok,
                            headers: Object.fromEntries(response.headers.entries()),
                            contentType: contentType,
                            imageData: base64String
                        };
                    } else {
                        // Handle text/JSON response
                        const responseText = await response.text();
                        
                        return {
                            status: response.status,
                            ok: response.ok,
                            headers: Object.fromEntries(response.headers.entries()),
                            contentType: contentType,
                            body: responseText
                        };
                    }
                } catch (error) {
                    return {
                        error: error.message
                    };
                }
            }
        """, payload)
        
        print(f"API Response Status: {result.get('status', 'Unknown')}")
        content_type = result.get('contentType', '')
        
        if result.get('ok'):
            if 'image' in content_type:
                # Handle image response
                print(f"Received image response: {content_type}")
                image_data = result.get('imageData')
                
                if image_data:
                    # Decode base64 and save as PNG
                    image_bytes = base64.b64decode(image_data)
                    
                    # Create filename with timestamp
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    safe_prompt = "".join(c for c in prompt if c.isalnum() or c in (' ', '-', '_')).rstrip()[:50]
                    filename = f"generated_image_{timestamp}_{safe_prompt.replace(' ', '_')}.png"
                    
                    # Save the image
                    with open(filename, 'wb') as f:
                        f.write(image_bytes)
                    
                    print(f"✅ Image saved as: {filename}")
                    print(f"📁 File size: {len(image_bytes)} bytes")
                    
                    # Get absolute path
                    abs_path = os.path.abspath(filename)
                    print(f"📍 Full path: {abs_path}")
                else:
                    print("❌ No image data received")
            else:
                # Handle text/JSON response
                try:
                    response_data = json.loads(result['body'])
                    print("API Response (JSON):", json.dumps(response_data, indent=2))
                except:
                    print("API Response (Text):", result['body'])
        else:
            print(f"API Error: {result.get('body', result.get('error', 'Unknown error'))}")
            
    except Exception as e:
        print(f"Error making API request: {e}")

async def open_multimodal_site():
    """
    Opens multi-modal.ai.cloudflare.com in a GUI browser using Playwright
    """
    async with async_playwright() as p:
        # Launch browser with GUI (headless=False)
        browser = await p.chromium.launch(
            headless=False,  # Show the browser GUI
            args=[
                '--window-size=1280,720'
            ]
        )
        
        try:
            # Create a new page
            page = await browser.new_page()
            
            # Set viewport size
            await page.set_viewport_size({"width": 1280, "height": 720})
            
            # Navigate to the website
            print("Opening multi-modal.ai.cloudflare.com...")
            await page.goto('https://multi-modal.ai.cloudflare.com', 
                          wait_until='networkidle',  # Wait until network is idle
                          timeout=30000)  # 30 second timeout
            
            print("Website loaded successfully!")
            
            # Make the API request
            await make_api_request(page)
            
            print("Browser will stay open. Close it manually when done.")
            
            # Keep the browser open - you can add more interactions here
            input("Press Enter to close the browser...")
            
        except Exception as e:
            print(f"Error occurred: {e}")
        
        finally:
            # Close the browser
            await browser.close()

async def main():
    """
    Main function that allows user to input a custom prompt
    """
    # Get custom prompt from user
    custom_prompt = input("Enter your prompt (or press Enter for default 'purple clouds'): ").strip()
    
    if not custom_prompt:
        custom_prompt = "A detailed oil painting of purple clouds"
    
    print(f"Using prompt: '{custom_prompt}'")
    
    # Launch browser and make request
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=False,
            args=[
                '--window-size=1280,720',
                '--disable-blink-features=AutomationControlled',
                '--disable-web-security',
                '--disable-features=VizDisplayCompositor'
            ]
        )
        
        try:
            # Create context with additional stealth settings
            context = await browser.new_context(
                viewport={"width": 1280, "height": 720},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
            
            page = await context.new_page()
            
            # Add stealth settings to avoid detection
            await page.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined,
                });
                
                window.chrome = {
                    runtime: {},
                };
                
                Object.defineProperty(navigator, 'plugins', {
                    get: () => [1, 2, 3, 4, 5],
                });
            """)
            
            print("Opening multi-modal.ai.cloudflare.com...")
            await page.goto('https://multi-modal.ai.cloudflare.com', 
                          wait_until='networkidle',
                          timeout=30000)
            
            print("Website loaded successfully!")
            
            # Wait for any Cloudflare challenges to complete
            print("Waiting for page to fully load and any security checks...")
            await asyncio.sleep(5)
            
            # Check if we're still on the main page (not blocked)
            current_url = page.url
            if "cloudflare" in await page.title() and "blocked" in (await page.content()).lower():
                print("Cloudflare blocked the request. Please solve any captcha manually in the browser.")
                input("Press Enter after solving any captcha or security check...")
            
            # Make the API request with custom prompt
            await make_api_request(page, custom_prompt)
            
            print("Browser will stay open. Close it manually when done.")
            input("Press Enter to close the browser...")
            
        except Exception as e:
            print(f"Error occurred: {e}")
        finally:
            await browser.close()

if __name__ == "__main__":
    asyncio.run(main())