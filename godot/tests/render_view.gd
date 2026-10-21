extends SceneTree
## Manual visual check of the window view (opens a window, not run by the test suite):
##   godot --path godot --script res://tests/render_view.gd -- --out=/tmp/view.png
## Builds a sample world through WorldApi, lets some flights progress, saves a screenshot and quits.

var frames := 0
var out := "user://view.png"


func _init() -> void:
	for arg in OS.get_cmdline_user_args():
		if arg.begins_with("--out="):
			out = arg.get_slice("=", 1)
	var world := Node2D.new()
	root.add_child(world)
	var api := WorldApi.new(world, WorldApi.DEFAULT_SIZE, {"flight_speed_factor": 1.0})
	var add := func(cmd: String, args: Dictionary): return api.handle(cmd, args).result
	var tree = add.call("add_habitat", {"type": "tree_cavity", "x": 820, "y": 160})
	add.call("add_habitat", {"type": "hive_box", "x": 150, "y": 600})
	var soil = add.call("add_habitat", {"type": "bare_soil", "x": 700, "y": 520})
	add.call("add_habitat", {"type": "hollow_stem", "x": 350, "y": 200})
	var wood = add.call("add_habitat", {"type": "dead_wood", "x": 520, "y": 620})
	add.call("add_habitat", {"type": "rodent_burrow", "x": 250, "y": 420})
	var s = add.call("add_swarm", {"x": 450, "y": 330, "population": 12000, "name": "Essaim A"})
	add.call("add_swarm", {"x": 600, "y": 120, "population": 8000})
	var m = add.call("add_bee", {"species": "mining_bee", "x": 100, "y": 100})
	add.call("add_bee", {"species": "mining_bee", "x": 690, "y": 500})
	var c = add.call("add_bee", {"species": "carpenter_bee", "x": 900, "y": 400})
	add.call("add_bee", {"species": "mason_bee", "x": 900, "y": 650})
	api.handle("remove_entity", {"id": add.call("add_habitat", {"type": "hollow_stem", "x": 1, "y": 1}).id})
	api.handle("resume", {})
	api.handle("apply_decision", {"bee_id": s.id, "habitat_id": tree.id})
	api.handle("apply_decision", {"bee_id": m.id, "habitat_id": soil.id})
	api.handle("apply_decision", {"bee_id": c.id, "habitat_id": wood.id})
	for i in 60:
		api.step()
	var view: Node2D = load("res://view/world_view.gd").new()
	view.setup(api, "http://localhost:8000")
	root.add_child(view)


func _process(_delta: float) -> bool:
	frames += 1
	if frames == 10:
		root.get_texture().get_image().save_png(out)
		print("saved ", out)
		return true
	return false
