$env:PS_API_HOST = if ($env:PS_API_HOST) { $env:PS_API_HOST } else { "127.0.0.1" }
$env:PS_API_PORT = if ($env:PS_API_PORT) { $env:PS_API_PORT } else { "8000" }
python -u -m app.main
