
import glob,os
from datetime import datetime, timedelta, date
import time
import requests
from io import BytesIO, DEFAULT_BUFFER_SIZE
import struct
from lzma import LZMADecompressor, LZMAError, FORMAT_AUTO
import threading

URL = "https://datafeed.dukascopy.com/datafeed/{currency}/{year}/{month:02d}/{day:02d}/{hour:02d}h_ticks.bi5"

def wget(symbol, day, hour):
	url_info = {
		'currency': symbol,
		'year': day.year,
		'month': day.month - 1,
		'day': day.day
	}
	url = URL.format(**url_info, hour=hour)
	buffer = BytesIO()
	id = url[35:].replace('/', " ")
	start = time.time()
	print("Fetching {0}".format(id))
	for i in range(3):
		try:
			res = requests.get(url, stream=True)
			if res.status_code == 200:
				for chunk in res.iter_content(DEFAULT_BUFFER_SIZE):
					buffer.write(chunk)
				print("Fetched %s completed %dbytes in %ds" % (id, len(buffer.getbuffer()), time.time() - start))
				if len(buffer.getbuffer()) <= 0:
					print("Buffer for {0} is empty ".format(id))
				return buffer.getbuffer()
			elif res.status_code == 404:
				return buffer.getbuffer()
			else:
				print("Request to {0} failed with error code : {1} ".format(url, str(res.status_code)))
		except Exception as e:
			print("Request {0} failed with exception : {1}".format(id, str(e)))
			time.sleep(0.1)

	raise Exception("Request failed for {0} after ATTEMPTS attempts".format(url))


def decompress_lzma(data):
	results = []
	len(data)
	while True:
		decomp = LZMADecompressor(FORMAT_AUTO, None, None)
		try:
			res = decomp.decompress(data)
		except LZMAError:
			if results:
				break  # Leftover data is not a valid LZMA/XZ stream; ignore it.
			else:
				raise  # Error on the first iteration; bail out.
		results.append(res)
		data = decomp.unused_data
		if not data:
			break
		if not decomp.eof:
			raise LZMAError("Compressed data ended before the end-of-stream marker was reached")
	return b"".join(results)


def tokenize(buffer):
	token_size = 20
	size = int(len(buffer) / token_size)
	tokens = []
	for i in range(0, size):
		tokens.append(struct.unpack('!IIIff', buffer[i * token_size: (i + 1) * token_size]))
	return tokens

def decompress(compressed_buffer):
	if compressed_buffer.nbytes == 0:
		return compressed_buffer
	return tokenize(decompress_lzma(compressed_buffer))

def normalize(day, hour, ticks):
	def norm(time, ask, bid, volume_ask, volume_bid):
		date = datetime(day.year, day.month, day.day, hour) + timedelta(milliseconds=time)
		return date.strftime("%Y-%m-%d %H:%M:%S.%f"), ask / 1000, bid / 1000, round(volume_ask * 1000000), round(volume_bid * 1000000)

	return list(map(lambda x: norm(*x), ticks))

def tickstring(ticks):
	return list(map(lambda x: "%s,%.3f,%.3f,%d,%d" % x, ticks))

def writeFile(wfn, lines):
	try:
		wt = (("\n".join(lines)).strip()+"\n")
		wf = open(wfn, "w")
		wf.write(wt)
		wf.close()
		print("write file", wfn, "ok")
	except Exception as e:
		print("write file error, ", e)

def duka1day(symbol, day, path):
	lines = []
	for hour in range(24):
		buf = wget(symbol, day, hour)
		lines += tickstring(normalize(day, hour, decompress(buf)))
	writeFile("%s%s-%s.csv" % (path, symbol, day.strftime("%Y-%m-%d")), lines)

def dukascopy(symbol, day, dayend, path):
	threads = []
	while day<dayend:
		while len(threads)>10:
			time.sleep(0.001)
			for t in threads:
				if not t.isAlive():
					threads.remove(t)
		t = threading.Thread(target=duka1day, args=(symbol, day, path, ))
		t.start()
		threads.append(t)
		day += timedelta(days=1)
		
	for t in threads:
		t.join()
	
if __name__ == '__main__':
	symbol = "XAUUSD"
	from_date = "2003-05-05"
	files = glob.glob("data/%s-*.csv" % symbol)
	if len(files)>0:
		files.sort(reverse=True)
		from_date = files[0][5:][7:17]
	day = datetime.strptime(from_date,"%Y-%m-%d").date()
	dukascopy(symbol, day, date.today(), "data/")
	