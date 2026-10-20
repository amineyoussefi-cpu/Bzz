extends Node2D
## The 2D world. Listens on 127.0.0.1 for newline-delimited JSON commands:
##   request:  {"id": 1, "cmd": "ping", "args": {}}
##   response: {"id": 1, "ok": true, "result": ...} or {"id": 1, "ok": false, "error": "..."}
## World commands are handled by WorldApi (godot/api/world_api.gd); see docs/api.md.

var server := TCPServer.new()
var peers: Array[StreamPeerTCP] = []
var buffers := {}  # StreamPeerTCP -> PackedByteArray
var api: WorldApi


func _ready() -> void:
	var port := 9876
	var host := "127.0.0.1"  # use --host=0.0.0.0 in a container so other services can connect
	var size := WorldApi.DEFAULT_SIZE
	var params := {}  # other --key=value args: simulation parameters (WorldApi.DEFAULT_CONFIG)
	for arg in OS.get_cmdline_user_args():
		var value := arg.get_slice("=", 1)
		if arg.begins_with("--port="):
			port = int(value)
		elif arg.begins_with("--host="):
			host = value
		elif arg.begins_with("--world-width="):
			size.x = float(value)
		elif arg.begins_with("--world-height="):
			size.y = float(value)
		elif arg.begins_with("--") and "=" in arg:
			params[arg.get_slice("=", 0).trim_prefix("--").replace("-", "_")] = value
	var config_err := WorldApi.config_error(params)
	if size.x <= 0 or size.y <= 0 or config_err:
		push_error(config_err if config_err else "world size must be positive, got %s" % size)
		get_tree().quit(1)
		return
	api = WorldApi.new(self, size, params)
	var err := server.listen(port, host)
	if err != OK:
		push_error("listen failed on port %d: %s" % [port, error_string(err)])
		get_tree().quit(1)
		return
	print("BZZ READY %s:%d world=%dx%d" % [host, port, size.x, size.y])


func _physics_process(_delta: float) -> void:
	api.step()


func _process(_delta: float) -> void:
	while server.is_connection_available():
		var peer := server.take_connection()
		peers.append(peer)
		buffers[peer] = PackedByteArray()
	for peer: StreamPeerTCP in peers.duplicate():
		peer.poll()
		if peer.get_status() != StreamPeerTCP.STATUS_CONNECTED:
			peers.erase(peer)
			buffers.erase(peer)
			continue
		var n := peer.get_available_bytes()
		if n > 0:
			buffers[peer].append_array(peer.get_data(n)[1])
		var buf: PackedByteArray = buffers[peer]
		var nl := buf.find(10)
		while nl != -1:
			var line := buf.slice(0, nl).get_string_from_utf8()
			buf = buf.slice(nl + 1)
			_reply(peer, _handle(line))
			nl = buf.find(10)
		buffers[peer] = buf


func _handle(line: String) -> Dictionary:
	var req = JSON.parse_string(line)
	if typeof(req) != TYPE_DICTIONARY:
		return {"id": null, "ok": false, "error": "invalid JSON object"}
	var id = req.get("id")
	var args = req.get("args", {})
	if typeof(args) != TYPE_DICTIONARY:
		return {"id": id, "ok": false, "error": "args must be an object"}
	match req.get("cmd"):
		"ping":
			return {"id": id, "ok": true, "result": "pong"}
		"quit":
			get_tree().quit.call_deferred()
			return {"id": id, "ok": true, "result": "bye"}
	var resp := api.handle(str(req.get("cmd")), args)
	resp["id"] = id
	return resp


func _reply(peer: StreamPeerTCP, resp: Dictionary) -> void:
	peer.put_data((JSON.stringify(resp) + "\n").to_utf8_buffer())
