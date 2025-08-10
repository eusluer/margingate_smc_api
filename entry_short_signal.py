import pandas as pd
import numpy as np
import requests
import json
import time
from datetime import datetime, timedelta
import warnings
warnings.filterwarnings('ignore')

class BearishCHOCHAnalyzer:
    """30 dakikalık ve 15 dakikalık grafikte Bearish CHOCH (Change of Character) analizi yapan sınıf"""
    
    def __init__(self, symbol, interval="30m", limit=200):
        self.symbol = symbol
        self.interval = interval
        self.limit = limit
        self.data = None
        self.swing_lows = []
        self.swing_highs = []
        self.last_choch = None
        self.choch_signals = []
        
    def fetch_binance_data(self):
        """Binance'den veri çek"""
        url = "https://fapi.binance.com/fapi/v1/klines"
        params = {
            'symbol': self.symbol,
            'interval': self.interval,
            'limit': self.limit
        }
        
        try:
            response = requests.get(url, params=params)
            response.raise_for_status()
            data = response.json()
            
            df = pd.DataFrame(data, columns=[
                'timestamp', 'open', 'high', 'low', 'close', 'volume',
                'close_time', 'quote_asset_volume', 'number_of_trades',
                'taker_buy_base_asset_volume', 'taker_buy_quote_asset_volume', 'ignore'
            ])
            
            for col in ['open', 'high', 'low', 'close', 'volume']:
                df[col] = pd.to_numeric(df[col])
            
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            df.set_index('timestamp', inplace=True)
            
            self.data = df[['open', 'high', 'low', 'close', 'volume']].copy()
            self.data.columns = ['Open', 'High', 'Low', 'Close', 'Volume']
            
            return True
            
        except Exception as e:
            print(f"❌ {self.symbol} veri çekme hatası: {e}")
            return False
    
    def find_swing_points(self, lookback=5):
        """Swing high ve swing low noktalarını tespit et"""
        self.swing_lows = []
        self.swing_highs = []
        
        for i in range(lookback, len(self.data) - lookback):
            # Swing Low tespiti
            current_low = self.data['Low'].iloc[i]
            left_lows = self.data['Low'].iloc[i-lookback:i]
            right_lows = self.data['Low'].iloc[i+1:i+lookback+1]
            
            if current_low < left_lows.min() and current_low < right_lows.min():
                self.swing_lows.append({
                    'price': current_low,
                    'index': i,
                    'timestamp': self.data.index[i]
                })
            
            # Swing High tespiti
            current_high = self.data['High'].iloc[i]
            left_highs = self.data['High'].iloc[i-lookback:i]
            right_highs = self.data['High'].iloc[i+1:i+lookback+1]
            
            if current_high > left_highs.max() and current_high > right_highs.max():
                self.swing_highs.append({
                    'price': current_high,
                    'index': i,
                    'timestamp': self.data.index[i]
                })
    
    def detect_bearish_choch(self):
        """Bearish CHOCH (Change of Character) tespiti - Yükseliş trendinden düşüş trendine geçiş"""
        self.choch_signals = []
        
        if len(self.swing_lows) < 2 or len(self.swing_highs) < 2:
            return
        
        # Son swing high'ları kontrol et
        for i in range(1, len(self.swing_highs)):
            prev_high = self.swing_highs[i-1]
            curr_high = self.swing_highs[i]
            
            # Yükseliş trendi: Yeni high, öncekinden yüksek
            if curr_high['price'] > prev_high['price']:
                # Bu high'dan sonra gelen swing low'ları kontrol et
                for swing_low in self.swing_lows:
                    if swing_low['timestamp'] > curr_high['timestamp']:
                        # Bu swing low'ın kırılıp kırılmadığını kontrol et
                        break_index = swing_low['index']
                        
                        for j in range(break_index + 1, len(self.data)):
                            if self.data['Close'].iloc[j] < swing_low['price']:
                                # BEARISH CHOCH gerçekleşti!
                                choch_signal = {
                                    'type': 'BEARISH_CHOCH',
                                    'swing_high': curr_high['price'],
                                    'swing_low': swing_low['price'],
                                    'break_price': self.data['Close'].iloc[j],
                                    'break_timestamp': self.data.index[j],
                                    'choch_level': swing_low['price']
                                }
                                self.choch_signals.append(choch_signal)
                                break
                        break
    
    def check_active_signals(self, distance_pct=2.0):
        """Aktif sinyalleri kontrol et - Fiyat CHOCH seviyesinden %2 uzaklaşmadıysa sinyal aktif"""
        if not self.choch_signals:
            return None
        
        current_price = self.data['Close'].iloc[-1]
        active_signals = []
        
        for signal in self.choch_signals:
            choch_level = signal['choch_level']
            distance = abs((current_price - choch_level) / choch_level * 100)
            
            if distance <= distance_pct:
                signal_info = {
                    'symbol': self.symbol,
                    'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    'signal_type': 'BEARISH_CHOCH',
                    'choch_level': float(round(choch_level, 4)),
                    'current_price': float(round(current_price, 4)),
                    'distance_pct': float(round(distance, 2)),
                    'max_distance_pct': distance_pct,
                    'signal_active': True,
                    'break_timestamp': signal['break_timestamp'].strftime('%Y-%m-%d %H:%M:%S'),
                    'interval': self.interval
                }
                active_signals.append(signal_info)
        
        # En son sinyali döndür
        return active_signals[-1] if active_signals else None

def load_coins_from_json(filename='coins.json'):
    """coins.json dosyasından coin listesini yükle"""
    try:
        with open(filename, 'r') as f:
            coins_config = json.load(f)
            return coins_config.get('symbols', [])
    except Exception as e:
        print(f"❌ {filename} dosyası okunamadı: {e}")
        return []

def check_coin_above_range(symbol):
    """Belirli bir coin'in 2h ve 4h chartta range üstünde olup olmadığını kontrol et"""
    from primary_test import SimplifiedSMC
    
    above_range_timeframes = []
    
    # 4h kontrolü
    try:
        smc_4h = SimplifiedSMC(symbol, interval="4h", limit=500)
        if smc_4h.analyze():
            signal_4h = smc_4h.get_signal_json()
            if signal_4h and signal_4h.get('current_price', 0) > signal_4h.get('range_high', 0):
                above_range_timeframes.append('4h')
    except Exception as e:
        pass
    
    # 2h kontrolü  
    try:
        smc_2h = SimplifiedSMC(symbol, interval="2h", limit=500)
        if smc_2h.analyze():
            signal_2h = smc_2h.get_signal_json()
            if signal_2h and signal_2h.get('current_price', 0) > signal_2h.get('range_high', 0):
                above_range_timeframes.append('2h')
    except Exception as e:
        pass
        
    return above_range_timeframes

def get_long_signals_from_primary(coin_symbols):
    """primary_test.py'den long sinyalleri al"""
    from primary_test import SimplifiedSMC
    
    range_ici = []  # Range içinde olanlar (range_50 = true)
    entry_sinyali = []  # Entry sinyali olanlar (15m CHOCH var)
    
    for symbol in coin_symbols:
        try:
            # 4h ve 2h için long analizi
            for interval in ['4h', '2h']:
                smc = SimplifiedSMC(symbol, interval, 500)
                if smc.analyze():
                    signal = smc.get_signal_json()
                    if signal and signal.get('range_50'):  # Range içinde ve %50 altında
                        range_ici.append({
                            'symbol': symbol,
                            'interval': interval,
                            'current_price': signal['current_price'],
                            'range_position_pct': signal['range_position_pct']
                        })
            
            # 15m CHOCH analizi (entry_long_signal.py mantığı)
            from entry_long_signal import CHOCHAnalyzer
            analyzer_15m = CHOCHAnalyzer(symbol, interval="15m", limit=200)
            if analyzer_15m.fetch_binance_data():
                analyzer_15m.find_swing_points(lookback=3)
                analyzer_15m.detect_bullish_choch()
                choch_signal = analyzer_15m.check_active_signals(distance_pct=2.0)
                if choch_signal:
                    entry_sinyali.append({
                        'symbol': symbol,
                        'current_price': choch_signal['current_price'],
                        'choch_level': choch_signal['choch_level']
                    })
                    
        except Exception:
            continue
    
    return range_ici, entry_sinyali

def analyze_all_coins_for_signals(coin_symbols):
    """Tüm coinleri tarayıp short ve long sinyalleri bul"""
    short_signals = []
    
    print(f"🔍 {len(coin_symbols)} coin taranıyor...")
    
    for idx, symbol in enumerate(coin_symbols, 1):
        print(f"[{idx}/{len(coin_symbols)}] {symbol}", end=" ")
        
        try:
            # Short sinyal kontrolü
            above_range_timeframes = check_coin_above_range(symbol)
            
            if above_range_timeframes:
                # CHOCH analizi yap
                analyzer_30m = BearishCHOCHAnalyzer(symbol, interval="30m", limit=200)
                signal_30m = None
                if analyzer_30m.fetch_binance_data():
                    analyzer_30m.find_swing_points(lookback=3)
                    analyzer_30m.detect_bearish_choch()
                    signal_30m = analyzer_30m.check_active_signals(distance_pct=2.0)
                
                analyzer_15m = BearishCHOCHAnalyzer(symbol, interval="15m", limit=200)
                signal_15m = None
                if analyzer_15m.fetch_binance_data():
                    analyzer_15m.find_swing_points(lookback=3)
                    analyzer_15m.detect_bearish_choch()
                    signal_15m = analyzer_15m.check_active_signals(distance_pct=2.0)
                
                if signal_30m or signal_15m:
                    short_signals.append({
                        'symbol': symbol,
                        'timeframes': above_range_timeframes,
                        'choch_30m': signal_30m['choch_level'] if signal_30m else None,
                        'choch_15m': signal_15m['choch_level'] if signal_15m else None
                    })
                    print("✅ SHORT")
                else:
                    print("⏭️")
            else:
                print("⏭️")
            
            time.sleep(0.3)
            
        except Exception:
            print("❌")
            continue
    
    return short_signals

def main():
    """Ana fonksiyon"""
    print("🚀 Sinyal Tarayıcısı Başlatılıyor...")
    
    # coins.json'dan coin listesini yükle
    coin_symbols = load_coins_from_json('coins.json')
    
    if not coin_symbols:
        print("❌ coins.json yüklenemedi!")
        return
    
    print(f"📋 {len(coin_symbols)} coin taranacak")
    
    # Short sinyalleri al
    short_signals = analyze_all_coins_for_signals(coin_symbols)
    
    print(f"\n📊 Long sinyalleri alınıyor...")
    # Long sinyalleri al
    range_ici, entry_sinyali = get_long_signals_from_primary(coin_symbols)
    
    # Sonuçları hazırla
    results = {
        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'total_coins_scanned': len(coin_symbols),
        'short_signals': {
            'count': len(short_signals),
            'coins': short_signals
        },
        'long_signals': {
            'range_ici': {
                'count': len(range_ici),
                'coins': range_ici
            },
            'entry_sinyali': {
                'count': len(entry_sinyali),
                'coins': entry_sinyali
            }
        }
    }
    
    # sonuc.json'a yaz
    with open('sonuc.json', 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    
    # Özet göster
    print(f"\n📊 SONUÇLAR:")
    print(f"🔴 Short: {len(short_signals)}")
    print(f"🟢 Long Range İçi: {len(range_ici)}")
    print(f"🟢 Long Entry: {len(entry_sinyali)}")
    print(f"💾 sonuc.json kaydedildi")

if __name__ == "__main__":
    main()