# MarginGate SMC API

SMC (Smart Money Concept) Trading Bot with Supabase integration for automated signal analysis.

## Features

- Automated trading signal analysis every 5 minutes
- Long/Short signal detection with SMC methodology
- Range analysis for 2H and 4H timeframes
- CHOCH (Change of Character) entry signals
- Automatic JSON results upload to Supabase Storage

## Environment Variables

Required environment variables for deployment:

```
SUPABASE_URL=https://muwqydzmponlsoagasnw.supabase.co
SUPABASE_SERVICE_ROLE_KEY=your_service_role_key_here
SUPABASE_BUCKET=margingate
```

## Railway Deployment

1. Fork this repository
2. Connect to Railway
3. Add the environment variables above
4. Deploy

The bot will automatically start running with 5-minute cycles.

## Local Development

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Copy environment file:
```bash
cp .env.example .env
```

3. Add your Supabase credentials to `.env`

4. Run the bot:
```bash
python main.py
```

## File Structure

- `main.py` - Main controller with Supabase integration
- `coins_async.py` - Coin list updates
- `primary_test.py` - SMC analysis and alarm detection
- `entry_long_signal.py` - Long entry signals (15m CHOCH)
- `entry_short_signal.py` - Short entry signals (30m/15m Bearish CHOCH)
- Output JSON files are automatically uploaded to Supabase Storage

## Generated Output Files

- `sonuc.json` - Main analysis results
- `alarm_4h.json` - 4H timeframe range alarms
- `alarm_2h.json` - 2H timeframe range alarms
- `entry_long_signals.json` - Long entry CHOCH signals
- `entry_short_signals.json` - Short entry signals
- `coins.json` - Active coin list