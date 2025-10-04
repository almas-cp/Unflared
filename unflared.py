import asyncio
import json
import base64
import os
from datetime import datetime
from playwright.async_api import async_playwright
from flask import Flask, request, jsonify, send_file
import threading
import time
import concurrent.futures

# Global variables to store browser and page
browser = None
page = None
playwright_instance = None
main_loop = None

app = Flask(__name__)

async def make_api_request(prompt="A detailed oil painting of purple clouds"):
    """
    Makes the API request to the inference endpoint with a customizable prompt
    """
    global page
    
    if not page:
        return {"success": False, "error": "Browser not initialized"}
    
    try:
        print(f"🔄 Starting image generation process...")
        
        # Check if page is still alive
        try:
            await page.title()
        except Exception as e:
            return {"success": False, "error": f"Browser page is not responsive: {str(e)}"}
        
        print(f"✅ Browser page is responsive")
        # Prepare the request payload
        payload = {
            "model": "@cf/bytedance/stable-diffusion-xl-lightning",
            "prompt": prompt,
            "num_steps": 4,
            "guidance": 1
        }
        
        print(f"🎯 Making API request with prompt: '{prompt}'")
        
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
        
        print(f"📊 API Response Status: {result.get('status', 'Unknown')}")
        print(f"📋 Content Type: {result.get('contentType', 'Unknown')}")
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
                    
                    return {
                        "success": True,
                        "message": "Image generated successfully",
                        "prompt": prompt,
                        "filename": filename,
                        "image_size": len(image_bytes),
                        "image_base64": image_data,
                        "file_path": abs_path,
                        "image_url": f"http://localhost:5000/get-image/{filename}"
                    }
                else:
                    return {"success": False, "error": "No image data received"}
            else:
                # Handle text/JSON response
                try:
                    response_data = json.loads(result['body'])
                    return {"success": False, "error": "Unexpected JSON response", "data": response_data}
                except:
                    return {"success": False, "error": "Unexpected text response", "data": result['body']}
        else:
            error_msg = result.get('body', result.get('error', 'Unknown error'))
            return {"success": False, "error": error_msg}
            
    except Exception as e:
        print(f"🚨 Error making API request: {e}")
        import traceback
        traceback.print_exc()
        return {"success": False, "error": str(e)}

async def initialize_browser():
    """
    Initialize the browser and navigate to the website
    """
    global browser, page, playwright_instance
    
    try:
        playwright_instance = await async_playwright().start()
        
        # Launch browser with GUI (headless=False)
        browser = await playwright_instance.chromium.launch(
            headless=False,
            args=[
                '--window-size=1280,720',
                '--disable-blink-features=AutomationControlled',
                '--disable-web-security',
                '--disable-features=VizDisplayCompositor'
            ]
        )
        
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
        
        print("🌐 Opening multi-modal.ai.cloudflare.com...")
        await page.goto('https://multi-modal.ai.cloudflare.com', 
                      wait_until='networkidle',
                      timeout=30000)
        
        print("✅ Website loaded successfully!")
        
        # Wait for any Cloudflare challenges to complete
        print("⏳ Waiting for page to fully load and any security checks...")
        await asyncio.sleep(5)
        
        # Check if we're still on the main page (not blocked)
        if "cloudflare" in await page.title() and "blocked" in (await page.content()).lower():
            print("🚨 Cloudflare blocked the request. Please solve any captcha manually in the browser.")
            print("⏸️  Server will wait for manual intervention...")
        
        print("🎯 Browser ready! Waiting for API requests...")
        return True
        
    except Exception as e:
        print(f"❌ Error initializing browser: {e}")
        return False

async def cleanup_browser():
    """
    Clean up browser resources
    """
    global browser, page, playwright_instance
    
    try:
        if page:
            await page.close()
        if browser:
            await browser.close()
        if playwright_instance:
            await playwright_instance.stop()
        print("🧹 Browser cleanup completed")
    except Exception as e:
        print(f"⚠️  Error during cleanup: {e}")

# Flask API endpoints
@app.route('/generate-image', methods=['POST'])
def generate_image_endpoint():
    """
    API endpoint to generate images
    """
    global main_loop
    
    try:
        # Get data from request
        data = request.get_json() or {}
        prompt = data.get('prompt', 'A detailed oil painting of purple clouds')
        
        print(f"📨 Received API request for prompt: '{prompt}'")
        
        # Check if browser is ready
        if not page or not browser or not main_loop:
            return jsonify({
                'success': False,
                'error': 'Browser not initialized. Please restart the server.'
            }), 503
        
        # Run the async function in the main event loop
        future = asyncio.run_coroutine_threadsafe(make_api_request(prompt), main_loop)
        result = future.result(timeout=120)  # 2 minute timeout
        
        if result.get('success'):
            print(f"✅ Successfully generated image: {result.get('filename')}")
            return jsonify(result)
        else:
            print(f"❌ Failed to generate image: {result.get('error')}")
            return jsonify(result), 400
            
    except concurrent.futures.TimeoutError:
        error_msg = "Request timeout - image generation took too long"
        print(f"⏰ {error_msg}")
        return jsonify({
            'success': False,
            'error': error_msg
        }), 408
    except Exception as e:
        error_msg = f"Server error: {str(e)}"
        print(f"🚨 {error_msg}")
        return jsonify({
            'success': False,
            'error': error_msg
        }), 500

@app.route('/health', methods=['GET'])
def health_check():
    """
    Health check endpoint
    """
    global page, browser
    
    browser_status = "ready" if (browser and page) else "not_ready"
    
    return jsonify({
        'status': 'healthy',
        'service': 'Unflared AI Image Generator',
        'browser_status': browser_status,
        'timestamp': datetime.now().isoformat()
    })

@app.route('/get-image/<filename>', methods=['GET'])
def get_image(filename):
    """
    Serve generated images
    """
    try:
        # Security check - only allow PNG files and prevent directory traversal
        if not filename.endswith('.png') or '/' in filename or '\\' in filename or '..' in filename:
            return jsonify({'error': 'Invalid filename'}), 400
        
        # Check if file exists
        if not os.path.exists(filename):
            return jsonify({'error': 'Image not found'}), 404
        
        print(f"📤 Serving image: {filename}")
        
        # Serve the image file
        return send_file(
            filename,
            mimetype='image/png',
            as_attachment=False,
            download_name=filename
        )
        
    except Exception as e:
        print(f"🚨 Error serving image {filename}: {e}")
        return jsonify({'error': 'Failed to serve image'}), 500

@app.route('/list-images', methods=['GET'])
def list_images():
    """
    List all generated images
    """
    try:
        # Get all PNG files in current directory
        png_files = [f for f in os.listdir('.') if f.endswith('.png') and f.startswith('generated_image_')]
        
        # Create list with file info
        images = []
        for filename in png_files:
            try:
                stat = os.stat(filename)
                images.append({
                    'filename': filename,
                    'size': stat.st_size,
                    'created': datetime.fromtimestamp(stat.st_ctime).isoformat(),
                    'url': f"http://localhost:5000/get-image/{filename}"
                })
            except Exception as e:
                print(f"⚠️ Error getting info for {filename}: {e}")
        
        # Sort by creation time (newest first)
        images.sort(key=lambda x: x['created'], reverse=True)
        
        return jsonify({
            'success': True,
            'count': len(images),
            'images': images
        })
        
    except Exception as e:
        print(f"🚨 Error listing images: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/status', methods=['GET'])
def status_check():
    """
    Detailed status endpoint
    """
    global page, browser
    
    return jsonify({
        'browser_initialized': browser is not None,
        'page_ready': page is not None,
        'service': 'Unflared AI Image Generator',
        'endpoints': [
            'POST /generate-image',
            'GET /get-image/<filename>',
            'GET /list-images',
            'GET /health',
            'GET /status'
        ]
    })

def run_flask_server():
    """
    Run the Flask server in a separate thread
    """
    print("🚀 Starting Flask server on http://localhost:5000")
    app.run(host='0.0.0.0', port=5000, debug=False, use_reloader=False)

async def main():
    """
    Main function that initializes browser and starts the server
    """
    global main_loop
    
    print("🎨 Unflared AI Image Generator")
    print("=" * 50)
    
    # Store the main event loop
    main_loop = asyncio.get_event_loop()
    
    # Initialize browser first
    if not await initialize_browser():
        print("❌ Failed to initialize browser. Exiting...")
        return
    
    # Start Flask server in a separate thread
    flask_thread = threading.Thread(target=run_flask_server, daemon=True)
    flask_thread.start()
    
    print("🎯 Server is ready!")
    print("📡 API Endpoints:")
    print("   POST http://localhost:5000/generate-image")
    print("   GET  http://localhost:5000/get-image/<filename>")
    print("   GET  http://localhost:5000/list-images")
    print("   GET  http://localhost:5000/health")
    print("   GET  http://localhost:5000/status")
    print("🌐 Browser window will stay open")
    print("⏹️  Press Ctrl+C to stop the server")
    
    try:
        # Keep the main thread alive
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        print("\n🛑 Shutting down server...")
        await cleanup_browser()
        print("👋 Goodbye!")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n🛑 Server stopped by user")
    except Exception as e:
        print(f"🚨 Fatal error: {e}")