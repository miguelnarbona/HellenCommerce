import sys
import os
import asyncio

# Add root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# Add fastapi_service to path
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'fastapi_service'))

try:
    # Import the main module
    from fastapi_service.main import app
    
    # Get the event loop and run the lifespan asynchronously to test initialization
    loop = asyncio.get_event_loop()
    
    async def test_lifespan():
        # This will trigger the lifespan initialization
        # We just need to create the app and call the lifespan
        print("✅ Successfully imported FastAPI app")
        print("✅ Testing ContextManager initialization...")
        
        # The lifespan is automatically executed when the app is created
        # We can't easily call it separately, but we can check if the global variables are set
        from fastapi_service.main import context_manager, orchestrator_instance
        if context_manager is not None:
            print(f"✅ ContextManager initialized: {type(context_manager)}")
        else:
            print("⚠️ ContextManager is None")
        
        if orchestrator_instance is not None:
            print(f"✅ Orchestrator initialized: {type(orchestrator_instance)}")
        else:
            print("⚠️ Orchestrator is None")
        
        print("✅ FastAPI initialization test completed!")

    # Run the test
    loop.run_until_complete(test_lifespan())
    
except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()