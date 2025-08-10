import pandas as pd
import numpy as np
import requests
import warnings
import json
import time
from datetime import datetime, timedelta
warnings.filterwarnings('ignore')

class SimplifiedSMC:
    def __init__(self, symbol="SOLUSDT", interval="4h", limit=500):
        self.symbol = symbol
        self.interval = interval
        self.limit = limit
        self.data = None
        self.weak_high = None
        self.last_bullish_bos = None
        self.swing_low = None
        self.range_low = None
        self.range_high = None
        self.current_position_pct = None
        self.signal = None  # Sinyal için yeni değişken
        self.swing_low_broken = False  # Swing low kırılma kontrolü
        
    def fetch_binance_data(self):
        """Binance Perpetual verilerini çek"""
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
            
            # DataFrame oluştur
            df = pd.DataFrame(data, columns=[
                'timestamp', 'open', 'high', 'low', 'close', 'volume',
                'close_time', 'quote_asset_volume', 'number_of_trades',
                'taker_buy_base_asset_volume', 'taker_buy_quote_asset_volume', 'ignore'
            ])
            
            # Veri tiplerini düzenle
            for col in ['open', 'high', 'low', 'close', 'volume']:
                df[col] = pd.to_numeric(df[col])
            
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            df.set_index('timestamp', inplace=True)
            
            # Sadece gerekli kolonları al
            self.data = df[['open', 'high', 'low', 'close', 'volume']].copy()
            self.data.columns = ['Open', 'High', 'Low', 'Close', 'Volume']
            
            return True
            
        except Exception as e:
            print(f"❌ {self.symbol} veri çekme hatası: {e}")
            return False
    
    def find_weak_high(self):
        """En yüksek değeri (Weak High) bul"""
        self.weak_high = {
            'price': self.data['High'].max(),
            'index': self.data['High'].idxmax(),
            'timestamp': self.data['High'].idxmax()
        }
    
    def find_last_bullish_bos(self):
        """Son bullish BOS'u bul (basitleştirilmiş swing high kırılması)"""
        # Swing high'ları tespit et (5 bar lookback)
        swing_highs = []
        lookback = 5
        
        for i in range(lookback, len(self.data) - lookback):
            current_high = self.data['High'].iloc[i]
            left_highs = self.data['High'].iloc[i-lookback:i]
            right_highs = self.data['High'].iloc[i+1:i+lookback+1]
            
            if current_high > left_highs.max() and current_high > right_highs.max():
                swing_highs.append({
                    'price': current_high,
                    'index': i,
                    'timestamp': self.data.index[i],
                    'crossed': False
                })
        
        # Swing high kırılmalarını bul (bullish BOS) - sadece weak high'dan ÖNCE olanlar
        bullish_bos_list = []
        
        for swing in swing_highs:
            swing_price = swing['price']
            swing_idx = swing['index']
            swing_time = swing['timestamp']
            
            # Sadece weak high'dan önce olan swing high'ları kontrol et
            if self.weak_high and swing_time >= self.weak_high['timestamp']:
                continue
            
            # Swing high'dan sonraki barları kontrol et
            for j in range(swing_idx + 1, len(self.data)):
                close_price = self.data['Close'].iloc[j]
                break_time = self.data.index[j]
                
                # Weak high'dan sonra kırılma olmamalı
                if self.weak_high and break_time > self.weak_high['timestamp']:
                    break
                
                if close_price > swing_price:  # Kırılma
                    bullish_bos_list.append({
                        'break_price': close_price,
                        'swing_price': swing_price,
                        'break_timestamp': break_time,
                        'swing_timestamp': swing_time,
                        'swing_index': swing_idx
                    })
                    break
        
        # Son bullish BOS'u al (weak high'dan önce olan)
        if bullish_bos_list:
            self.last_bullish_bos = bullish_bos_list[-1]
    
    def find_swing_low_in_range(self):
        """BOS swing high'ı ile Weak High arasındaki en düşük değeri gören mumu bul"""
        if not self.last_bullish_bos or not self.weak_high:
            return
        
        # BOS swing high zamanından Weak High'a kadar olan veriyi al
        bos_swing_time = self.last_bullish_bos['swing_timestamp']
        weak_high_time = self.weak_high['timestamp']
        
        if bos_swing_time < weak_high_time:
            range_data = self.data[bos_swing_time:weak_high_time]
        else:
            return
        
        if len(range_data) == 0:
            return
        
        # En düşük değeri (Low) bul ve o mumun tüm bilgilerini al
        min_low_price = range_data['Low'].min()
        min_low_timestamp = range_data['Low'].idxmin()
        
        # O mumun tüm değerlerini al
        swing_low_candle = range_data.loc[min_low_timestamp]
        
        self.swing_low = {
            'low': min_low_price,
            'open': swing_low_candle['Open'],
            'high': swing_low_candle['High'],
            'close': swing_low_candle['Close'],
            'timestamp': min_low_timestamp
        }
    
    def check_swing_low_break(self):
        """Range low'un (swing low'un en düşük değeri) weak high'dan sonra kırılıp kırılmadığını kontrol et"""
        if not self.swing_low or not self.weak_high:
            return
        
        # Weak high'dan sonraki veriyi al
        weak_high_time = self.weak_high['timestamp']
        data_after_weak_high = self.data[weak_high_time:]
        
        if len(data_after_weak_high) == 0:
            return
        
        # Range low seviyesi (swing low'un en düşük fitil değeri)
        range_low_level = self.swing_low['low']
        
        # Weak high'dan sonra range low'un altına kapanış olup olmadığını kontrol et
        for idx, row in data_after_weak_high.iterrows():
            if row['Close'] < range_low_level:
                self.swing_low_broken = True
                print(f"   ⚠️  Range Low ({range_low_level:.4f}) weak high sonrası kırıldı!")
                print(f"      Kırılma zamanı: {idx}, Kapanış: {row['Close']:.4f}")
                break
    
    def calculate_range_and_position(self):
        """Range hesapla ve güncel pozisyonu belirle"""
        if not self.swing_low or not self.last_bullish_bos:
            return
        
        # Range: Swing Low mumunun en düşük değeri ile BOS arasında
        self.range_low = self.swing_low['low']
        self.range_high = self.last_bullish_bos['swing_price']
        
        # Güncel fiyat
        current_price = self.data['Close'].iloc[-1]
        
        # Range kontrolü ve pozisyon hesaplama
        range_size = self.range_high - self.range_low
        range_mid = self.range_low + (range_size / 2)
        
        if self.range_low <= current_price <= self.range_high:
            # Range içinde
            position_in_range = current_price - self.range_low
            self.current_position_pct = (position_in_range / range_size) * 100
            status = "RANGE İÇİNDE"
            in_range = True
        elif current_price > self.range_high:
            # Range üstünde
            excess = current_price - self.range_high
            self.current_position_pct = 100 + (excess / range_size) * 100
            status = "RANGE ÜSTÜNDE"
            in_range = False
        else:
            # Range altında
            deficit = self.range_low - current_price
            self.current_position_pct = -(deficit / range_size) * 100
            status = "RANGE ALTINDA"
            in_range = False
        
        # Sinyal kontrolü: Range içinde ve %50'nin altında mı? VE swing low kırılmamış mı?
        range_50_signal = bool(in_range and current_price < range_mid and not self.swing_low_broken)
        
        # Sinyal JSON oluştur
        self.signal = {
            "symbol": self.symbol,
            "timestamp": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            "current_price": float(round(current_price, 4)),
            "range_low": float(round(self.range_low, 4)),
            "range_high": float(round(self.range_high, 4)),
            "range_mid": float(round(range_mid, 4)),
            "range_position_pct": float(round(self.current_position_pct, 2)),
            "in_range": bool(in_range),
            "status": status,
            "swing_low_broken": bool(self.swing_low_broken),
            "range_50": bool(range_50_signal),
            "signal": "BUY" if range_50_signal else "NO_SIGNAL",
            "weak_high": float(self.weak_high['price']) if self.weak_high else None  # EKLENDİ!
        }
    
    def analyze(self):
        """Ana analiz fonksiyonu (sessiz mod)"""
        if not self.fetch_binance_data():
            return False
        
        # 1. Weak High bul
        self.find_weak_high()
        
        # 2. Son Bullish BOS bul (weak high öncesi)
        self.find_last_bullish_bos()
        
        # 3. Swing Low bul
        self.find_swing_low_in_range()
        
        # 4. Swing Low kırılma kontrolü
        self.check_swing_low_break()
        
        # 5. Range hesapla
        self.calculate_range_and_position()
        
        return True
    
    def get_signal_json(self):
        """Sadece JSON sinyal döndür"""
        return self.signal if self.signal else None

def load_coins_config(filename='coins.json'):
    """Coin listesini yükle"""
    try:
        with open(filename, 'r') as f:
            return json.load(f)
    except Exception as e:
        print(f"❌ Coins dosyası okunamadı: {e}")
        return None

def scan_all_coins(coins_config, intervals=['4h'], save_to_file=True):
    """Tüm coinleri tara ve sinyalleri topla"""
    if not coins_config:
        return None
    
    symbols = coins_config.get('symbols', [])
    all_signals = {
        'scan_timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'total_symbols': len(symbols),
        'scanned_symbols': 0,
        'error_symbols': [],
        'active_signals': [],
        'all_results': []
    }
    
    # Her interval için ayrı alarm listesi
    alarms_by_interval = {}
    
    print(f"🚀 {len(symbols)} coin taranacak...")
    print("=" * 60)
    
    for idx, symbol in enumerate(symbols, 1):
        print(f"\n[{idx}/{len(symbols)}] {symbol} analiz ediliyor...")
        
        try:
            # Her interval için tara
            for interval in intervals:
                print(f"   📊 Interval: {interval}")
                
                # SMC analizi yap
                smc = SimplifiedSMC(symbol, interval, 500)
                
                if smc.analyze():
                    signal = smc.get_signal_json()
                    
                    if signal:
                        # Interval bilgisini ekle
                        signal['interval'] = interval
                        
                        # Sonuçları kaydet
                        all_signals['all_results'].append(signal)
                        
                        # Aktif sinyal varsa özel listeye ekle
                        if signal['range_50']:
                            all_signals['active_signals'].append({
                                'symbol': symbol,
                                'interval': interval,
                                'current_price': signal['current_price'],
                                'range_position_pct': signal['range_position_pct'],
                                'timestamp': signal['timestamp']
                            })
                            
                            # Interval bazlı alarm listesine ekle
                            if interval not in alarms_by_interval:
                                alarms_by_interval[interval] = {
                                    'scan_timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                                    'interval': interval,
                                    'total_alarms': 0,
                                    'alarms': []
                                }
                            
                            alarms_by_interval[interval]['alarms'].append({
                                'symbol': symbol,
                                'current_price': signal['current_price'],
                                'range_low': signal['range_low'],
                                'range_high': signal['range_high'],
                                'range_mid': signal['range_mid'],
                                'range_position_pct': signal['range_position_pct'],
                                'timestamp': signal['timestamp']
                            })
                            alarms_by_interval[interval]['total_alarms'] += 1
                            
                            print(f"   🚨 ALIM SİNYALİ AKTİF! Range içinde ve %50 altında")
                        elif signal['swing_low_broken']:
                            print(f"   ⛔ Sinyal iptal - Range low kırıldı")
                        else:
                            print(f"   ✅ Analiz tamamlandı - Sinyal yok")
                else:
                    print(f"   ❌ Analiz başarısız")
                    all_signals['error_symbols'].append({'symbol': symbol, 'interval': interval})
                
                # Rate limit için kısa bekleme
                time.sleep(0.5)
                
        except Exception as e:
            print(f"   ❌ Hata: {e}")
            all_signals['error_symbols'].append({'symbol': symbol, 'error': str(e)})
            continue
        
        all_signals['scanned_symbols'] += 1
    
    # Özet bilgi
    print("\n" + "=" * 60)
    print("📊 TARAMA ÖZETİ")
    print("=" * 60)
    print(f"✅ Taranan: {all_signals['scanned_symbols']}/{all_signals['total_symbols']}")
    print(f"🚨 Aktif Sinyal: {len(all_signals['active_signals'])}")
    print(f"❌ Hatalı: {len(all_signals['error_symbols'])}")
    
    if all_signals['active_signals']:
        print(f"\n🎯 AKTİF SİNYALLER:")
        for signal in all_signals['active_signals']:
            print(f"   - {signal['symbol']} ({signal['interval']}): ${signal['current_price']:.4f} - Range %{signal['range_position_pct']:.2f}")
    
    # Dosyaya kaydet
    if save_to_file:
        # Ana sonuç dosyası
        filename = "sonuc.json"
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(all_signals, f, indent=2, ensure_ascii=False)
        print(f"\n💾 Sonuçlar kaydedildi: {filename}")
        
        # Her interval için ayrı alarm dosyası
        for interval, alarm_data in alarms_by_interval.items():
            alarm_filename = f"alarm_{interval}.json"
            with open(alarm_filename, 'w', encoding='utf-8') as f:
                json.dump(alarm_data, f, indent=2, ensure_ascii=False)
            print(f"🔔 {interval} alarmları kaydedildi: {alarm_filename} ({alarm_data['total_alarms']} alarm)")
        
        # Short setup için 4h alarmı dosyası
        save_short_alarm_signals(all_signals["all_results"])
    
    return all_signals

def save_short_alarm_signals(all_results, filename="short_alarm_signal.json"):
    """
    4h chartta weak high tespit edilmiş ve
    range_high ile weak_high arasındaki mesafe range_high'ın %50'sinden fazlaysa
    short alarm kaydı oluşturur.
    """
    short_signals = []
    for signal in all_results:
        if (
            signal.get("interval") == "4h"
            and signal.get("range_high") is not None
            and signal.get("weak_high") is not None
        ):
            range_high = signal["range_high"]
            weak_high = signal["weak_high"]
            fark = abs(range_high - weak_high)
            oran = fark / range_high if range_high != 0 else 0
            if oran > 0.5:
                short_signals.append({
                    "symbol": signal["symbol"],
                    "interval": signal["interval"],
                    "range_high": range_high,
                    "weak_high": weak_high,
                    "distance_pct": round(oran*100, 2),
                    "timestamp": signal["timestamp"],
                    "current_price": signal["current_price"]
                })
    with open(filename, "w", encoding="utf-8") as f:
        json.dump({"short_signals": short_signals, "created_at": datetime.now().strftime('%Y-%m-%d %H:%M:%S')}, f, indent=2, ensure_ascii=False)
    print(f"\n🔻 Short alarm setup kaydedildi: {filename} ({len(short_signals)} sinyal)")

# Ana kullanım
if __name__ == "__main__":
    print("SMC Coin Scanner Başlatılıyor...")
    
    # Coins dosyasını yükle
    coins_config = load_coins_config('coins.json')
    
    if coins_config:
        # Birden fazla interval ile tarama (4h ve 2h)
        scan_all_coins(coins_config, intervals=['4h', '2h'])
    else:
        print("❌ coins.json dosyası bulunamadı!")
        print("ℹ️  Lütfen coins.json dosyasının aynı dizinde olduğundan emin olun.")