extends Node2D
## Empty 2D world. Listens on 127.0.0.1 for newline-delimited JSON commands:
##   request:  {"id": 1, "cmd": "ping", "args": {}}
##   response: {"id": 1, "ok": true, "result": ...} or {"id": 1, "ok": false, "error": "..."}

var server := TCPServer.new()
var peers: Array[StreamPeerTCP] = []
var buffers := {}  # StreamPeerTCP -> PackedByteArray


func _ready() -> void:
	var port := 9876
	for arg in OS.get_cmdline_user_args():
		if arg.begins_with("--port="):
			port = int(arg.get_slice("=", 1))
	var err := server.listen(port, "127.0.0.1")
	if err != OK:
		push_error("listen failed on port %d: %s" % [port, error_string(err)])
		get_tree().quit(1)
		return
	print("BZZ READY port=%d" % port)


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
	match req.get("cmd"):
		"ping":
			return {"id": id, "ok": true, "result": "pong"}
		"get_state":
			return {"id": id, "ok": true, "result": {
				"physics_frames": Engine.get_physics_frames(),
				"process_frames": Engine.get_process_frames(),
				"node_count": get_child_count(),
			}}
		"quit":
			get_tree().quit.call_deferred()
			return {"id": id, "ok": true, "result": "bye"}
		_:
			return {"id": id, "ok": false, "error": "unknown command: %s" % req.get("cmd")}


func _reply(peer: StreamPeerTCP, resp: Dictionary) -> void:
	peer.put_data((JSON.stringify(resp) + "\n").to_utf8_buffer())
