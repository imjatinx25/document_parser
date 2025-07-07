import os

# Valkey Glide client
valkey_client = None

async def get_valkey_client():
    """Get or create Valkey Glide client"""
    global valkey_client
    if valkey_client is None:
        try:
            from glide import (
                GlideClusterClient,
                GlideClusterClientConfiguration,
                Logger,
                LogLevel,
                NodeAddress,
            )
            
            # Set logger configuration
            Logger.set_logger_config(LogLevel.INFO)
            
            # Get Valkey configuration from environment variables
            valkey_host = os.getenv('VALKEY_HOST', 'localhost')
            valkey_port = int(os.getenv('VALKEY_PORT', 6379))
            use_tls = os.getenv('VALKEY_USE_TLS', 'false').lower() == 'true'
            
            # Configure the Glide Cluster Client
            addresses = [NodeAddress(valkey_host, valkey_port)]
            config = GlideClusterClientConfiguration(addresses=addresses, use_tls=use_tls)
            
            print(f"Connecting to Valkey Glide at {valkey_host}:{valkey_port}...")
            valkey_client = await GlideClusterClient.create(config)
            print("Valkey Glide connection successful")
            return valkey_client
            
        except Exception as e:
            raise e
    
    return valkey_client
