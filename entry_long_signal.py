import pandas as pd
import numpy as np
import requests
import json
import time
from datetime import datetime, timedelta
import warnings
warnings.filterwarnings('ignore')

class CHOCHAnalyzer:
    """15 dakikalık grafikte CHOCH (Change of Character) analizi yapan sınıf"""
    
    def __init__(self, symbol, interval="15m", limit=200):
        self.symbol = symbol
        self.interval = interval
        self.limit = limit
        self.data = None
        self.swing_lows = []
        self.swing_highs = []
        self.last_choch = None
        self.choch_signals = []
        
    def fetch_binance_data(self):
        """Binance'den 15 dakikalık veri çek"""
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
    
    def detect_bullish_choch(self):
        """Bullish CHOCH (Change of Character) tespiti - Düşüş trendinden yükseliş trendine geçiş"""
        self.choch_signals = []
        
        if len(self.swing_lows) < 2 or len(self.swing_highs) < 2:
            return
        
        # Son swing low'ları kontrol et
        for i in range(1, len(self.swing_lows)):
            prev_low = self.swing_lows[i-1]
            curr_low = self.swing_lows[i]
            
            # Düşüş trendi: Yeni low, öncekinden düşük
            if curr_low['price'] < prev_low['price']:
                # Bu low'dan sonra gelen swing high'ları kontrol et
                for swing_high in self.swing_highs:
                    if swing_high['timestamp'] > curr_low['timestamp']:
                        # Bu swing high'ın kırılıp kırılmadığını kontrol et
                        break_index = swing_high['index']
                        
                        for j in range(break_index + 1, len(self.data)):
                            if self.data['Close'].iloc[j] > swing_high['price']:
                                # CHOCH gerçekleşti!
                                choch_signal = {
                                    'type': 'BULLISH_CHOCH',
                                    'swing_low': curr_low['price'],
                                    'swing_high': swing_high['price'],
                                    'break_price': self.data['Close'].iloc[j],
                                    'break_timestamp': self.data.index[j],
                                    'choch_level': swing_high['price']
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
                    'signal_type': 'BULLISH_CHOCH',
                    'choch_level': float(round(choch_level, 4)),
                    'current_price': float(round(current_price, 4)),
                    'distance_pct': float(round(distance, 2)),
                    'max_distance_pct': distance_pct,
                    'signal_active': True,
                    'break_timestamp': signal['break_timestamp'].strftime('%Y-%m-%d %H:%M:%S')
                }
                active_signals.append(signal_info)
        
        # En son sinyali döndür
        return active_signals[-1] if active_signals else None

def load_alarm_files():
    """alarm_4h.json ve alarm_2h.json dosyalarını yükle"""
    alarm_coins = set()
    
    # 4h alarmları yükle
    try:
        with open('alarm_4h.json', 'r') as f:
            data_4h = json.load(f)
            for alarm in data_4h.get('alarms', []):
                alarm_coins.add(alarm['symbol'])
            print(f"✅ alarm_4h.json yüklendi: {len(data_4h.get('alarms', []))} coin")
    except Exception as e:
        print(f"⚠️  alarm_4h.json okunamadı: {e}")
    
    # 2h alarmları yükle
    try:
        with open('alarm_2h.json', 'r') as f:
            data_2h = json.load(f)
            for alarm in data_2h.get('alarms', []):
                alarm_coins.add(alarm['symbol'])
            print(f"✅ alarm_2h.json yüklendi: {len(data_2h.get('alarms', []))} coin")
    except Exception as e:
        print(f"⚠️  alarm_2h.json okunamadı: {e}")
    
    return list(alarm_coins)

def analyze_coins_for_entry(alarm_coins):
    """Alarm listesindeki coinleri 15m grafikte CHOCH için analiz et"""
    entry_signals = {
        'scan_timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'total_coins': len(alarm_coins),
        'analyzed_coins': 0,
        'active_signals': [],
        'all_results': []
    }
    
    print(f"\n🔍 {len(alarm_coins)} coin 15m grafikte CHOCH analizi için taranacak...")
    print("=" * 60)
    
    for idx, symbol in enumerate(alarm_coins, 1):
        print(f"\n[{idx}/{len(alarm_coins)}] {symbol} analiz ediliyor...")
        
        try:
            # CHOCH analizi yap
            analyzer = CHOCHAnalyzer(symbol, interval="15m", limit=200)
            
            if analyzer.fetch_binance_data():
                analyzer.find_swing_points(lookback=3)  # 15m için daha kısa lookback
                analyzer.detect_bullish_choch()
                
                # Aktif sinyalleri kontrol et
                active_signal = analyzer.check_active_signals(distance_pct=2.0)
                
                if active_signal:
                    entry_signals['active_signals'].append(active_signal)
                    entry_signals['all_results'].append(active_signal)
                    print(f"   🎯 CHOCH SİNYALİ AKTİF!")
                    print(f"      CHOCH Seviyesi: ${active_signal['choch_level']}")
                    print(f"      Güncel Fiyat: ${active_signal['current_price']}")
                    print(f"      Mesafe: %{active_signal['distance_pct']}")
                else:
                    print(f"   ✅ Analiz tamamlandı - Aktif CHOCH sinyali yok")
                    
                    # Sinyal olmasa bile sonucu kaydet
                    no_signal_result = {
                        'symbol': symbol,
                        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                        'signal_active': False,
                        'reason': 'No CHOCH or price moved away'
                    }
                    entry_signals['all_results'].append(no_signal_result)
            else:
                print(f"   ❌ Veri çekme hatası")
                
            entry_signals['analyzed_coins'] += 1
            
            # Rate limit için bekleme
            time.sleep(0.3)
            
        except Exception as e:
            print(f"   ❌ Analiz hatası: {e}")
            continue
    
    # Özet
    print("\n" + "=" * 60)
    print("📊 CHOCH ANALİZ ÖZETİ")
    print("=" * 60)
    print(f"✅ Analiz edilen: {entry_signals['analyzed_coins']}/{entry_signals['total_coins']}")
    print(f"🎯 Aktif CHOCH Sinyali: {len(entry_signals['active_signals'])}")
    
    if entry_signals['active_signals']:
        print(f"\n💎 AKTİF ENTRY SİNYALLERİ:")
        for signal in entry_signals['active_signals']:
            print(f"   - {signal['symbol']}: ${signal['current_price']:.4f} (CHOCH: ${signal['choch_level']:.4f}, Mesafe: %{signal['distance_pct']})")
    
    # Sonuçları kaydet
    with open('entry_long_signals.json', 'w', encoding='utf-8') as f:
        json.dump(entry_signals, f, indent=2, ensure_ascii=False)
    print(f"\n💾 Entry sinyalleri kaydedildi: entry_long_signals.json")
    
    return entry_signals

def main():
    """Ana fonksiyon"""
    print("🚀 Entry Long Sinyal Botu Başlatılıyor...")
    print("📌 15m grafikte CHOCH analizi yapılacak")
    
    # Alarm dosyalarını yükle
    alarm_coins = load_alarm_files()
    
    if not alarm_coins:
        print("\n❌ Hiç alarm bulunamadı!")
        print("ℹ️  Önce primary_test.py'yi çalıştırıp alarm oluşturun.")
        return
    
    print(f"\n📋 Toplam {len(alarm_coins)} benzersiz coin bulundu")
    print(f"🪙 Coinler: {', '.join(alarm_coins[:5])}{'...' if len(alarm_coins) > 5 else ''}")
    
    # Analiz yap
    analyze_coins_for_entry(alarm_coins)

if __name__ == "__main__":
    main()