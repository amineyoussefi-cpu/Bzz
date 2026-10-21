extends Node2D
## Read-only view of the world in the Godot window (window mode only; never loaded in headless mode).
## It draws, every frame, the state WorldApi already owns (entities, flights, swarm delays, clock) with simple shapes,
## and offers view-only interactions: pan, zoom, hover/click to inspect, F to fit the world.
## It never changes the world: every action goes through the dashboard, the backend and WorldApi's validation.

const HABITAT_SIZE := 26.0
const BEE_RADIUS := 8.0
const HABITAT_COLORS := {
	"tree_cavity": Color("#8a5a34"), "hive_box": Color("#e0a93a"), "rodent_burrow": Color("#a07850"),
	"bare_soil": Color("#d9bf86"), "hollow_stem": Color("#b5523a"), "dead_wood": Color("#6f5a45"),
}
const BEE_COLORS := {
	"honey_bee": Color("#d89a2b"), "bumblebee": Color("#1d1a17"), "mason_bee": Color("#c8552a"),
	"mining_bee": Color("#8d8a84"), "carpenter_bee": Color("#5b3fa0"),
}
const INK := Color("#2b2118")
const BACKGROUND := Color("#eef4e4")
const PAN_KEYS_SPEED := 600.0  # screen pixels per second
const ZOOM_STEP := 1.15

var api: WorldApi
var dashboard_url := ""
var camera := Camera2D.new()
var hud := Label.new()
var info := Label.new()
var empty_message := Label.new()
var font: Font
var selected_id := ""
var _dragging := false


func setup(p_api: WorldApi, p_dashboard_url := "") -> void:
	api = p_api
	dashboard_url = p_dashboard_url


func _ready() -> void:
	font = ThemeDB.fallback_font
	RenderingServer.set_default_clear_color(Color("#faf6ec"))
	add_child(camera)
	var layer := CanvasLayer.new()
	add_child(layer)
	for l: Label in [hud, info, empty_message]:
		l.add_theme_color_override("font_color", INK)
		l.add_theme_font_size_override("font_size", 15)
		var box := StyleBoxFlat.new()
		box.bg_color = Color(1, 1, 1, 0.88)
		box.set_content_margin_all(8)
		box.set_corner_radius_all(6)
		l.add_theme_stylebox_override("normal", box)
		layer.add_child(l)
	hud.position = Vector2(10, 10)
	info.visible = false
	empty_message.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	empty_message.text = "Le monde est vide.\nAjoutez des habitats, des abeilles et des essaims depuis le tableau de bord" \
		+ ("\n" + dashboard_url if dashboard_url else ".")
	fit_world()


## Zooms and centers the camera on the whole world.
func fit_world() -> void:
	var view := get_viewport_rect().size
	var z := minf(view.x / (api.size.x * 1.08), view.y / (api.size.y * 1.15))
	camera.zoom = Vector2(z, z)
	camera.position = api.size / 2 - Vector2(0, 30 / z)  # leave room for the info banner


# --- what to draw ---------------------------------------------------------------------------------

## One item per entity, built from WorldApi's own summaries (no simulation logic here).
func build_items() -> Array[Dictionary]:
	var items: Array[Dictionary] = []
	var fanned := {}  # habitat id -> settled occupants drawn so far
	for e in api.entities.values():
		var item := api._summary(e)
		item["pos"] = e.position
		if item.get("state") == "settled":
			var n: int = fanned.get(item.home_id, 0) + 1
			fanned[item.home_id] = n
			item["pos"] = e.position + Vector2.from_angle(n * 1.3) * (HABITAT_SIZE * 0.75)
		items.append(item)
	return items


func _process(delta: float) -> void:
	var pan := Input.get_vector("ui_left", "ui_right", "ui_up", "ui_down")
	if pan:
		camera.position += pan * PAN_KEYS_SPEED * delta / camera.zoom.x
	_update_labels()
	queue_redraw()


func _draw() -> void:
	draw_rect(Rect2(Vector2.ZERO, api.size), BACKGROUND)
	draw_rect(Rect2(Vector2.ZERO, api.size), INK.lerp(BACKGROUND, 0.6), false, 2.0 / camera.zoom.x)
	var items := build_items()
	for it in items:  # trajectories under everything else
		if it.get("state") == "flying":
			draw_dashed_line(it.pos, Vector2(it.target_x, it.target_y), Color(INK, 0.45), 1.5 / camera.zoom.x, 8.0)
	for it in items:
		match it.kind:
			"habitat": _draw_habitat(it)
	for it in items:
		match it.kind:
			"bee": _draw_bee(it)
			"swarm": _draw_swarm(it)
	if selected_id or _hovered():
		var it := _find(selected_id if selected_id else _hovered())
		if it:
			draw_arc(it.pos, 18.0, 0, TAU, 32, INK, 2.0 / camera.zoom.x)


func _text(pos: Vector2, s: String, size := 12, color := INK) -> void:
	draw_string(font, pos, s, HORIZONTAL_ALIGNMENT_LEFT, -1, size, color)


func _draw_habitat(it: Dictionary) -> void:
	var p: Vector2 = it.pos
	var c: Color = HABITAT_COLORS.get(it.type, Color.GRAY)
	var h := HABITAT_SIZE
	match it.type:
		"tree_cavity":
			draw_circle(p + Vector2(0, -h * 0.75), h * 0.55, Color("#5d8c45"))
			draw_rect(Rect2(p - Vector2(h * 0.3, h * 0.5), Vector2(h * 0.6, h)), c)
			draw_circle(p + Vector2(0, -h * 0.1), h * 0.13, Color("#3a2414"))
		"hive_box":
			draw_rect(Rect2(p - Vector2(h * 0.45, h * 0.35), Vector2(h * 0.9, h * 0.8)), c)
			draw_colored_polygon(PackedVector2Array([p + Vector2(-h * 0.55, -h * 0.35), p + Vector2(h * 0.55, -h * 0.35),
				p + Vector2(0, -h * 0.7)]), Color("#b5523a"))
			draw_rect(Rect2(p + Vector2(-h * 0.15, h * 0.3), Vector2(h * 0.3, h * 0.08)), Color("#3a2414"))
		"rodent_burrow":
			draw_circle(p, h * 0.5, c)
			draw_circle(p + Vector2(0, h * 0.1), h * 0.18, Color("#3a2414"))
		"bare_soil":
			draw_set_transform(p, 0, Vector2(1.4, 0.7))
			draw_circle(Vector2.ZERO, h * 0.6, c)
			draw_set_transform(Vector2.ZERO)
			for d in [Vector2(-8, -3), Vector2(2, 4), Vector2(9, -2), Vector2(-3, 6)]:
				draw_circle(p + d, 1.8, Color("#3a2414"))
		"hollow_stem":
			draw_rect(Rect2(p - Vector2(h * 0.45, h * 0.45), Vector2(h * 0.9, h * 0.9)), c)
			for i in 3:
				for j in 3:
					draw_circle(p + Vector2((i - 1) * h * 0.28, (j - 1) * h * 0.28), h * 0.09, Color("#3a2414"))
		"dead_wood":
			draw_rect(Rect2(p - Vector2(h * 0.7, h * 0.25), Vector2(h * 1.4, h * 0.5)), c)
			draw_circle(p + Vector2(h * 0.7, 0), h * 0.25, Color("#c9a679"))
		_:
			draw_rect(Rect2(p - Vector2(h, h) / 2, Vector2(h, h)), c)
	_text(p + Vector2(-h * 0.6, h * 0.95), "%s  %d/%d" % [it.id, it.occupants, it.capacity], 11)


func _draw_bee(it: Dictionary) -> void:
	var p: Vector2 = it.pos
	var c: Color = BEE_COLORS.get(it.species, Color.GRAY)
	match it.state:
		"waiting":  # no compatible habitat in the world
			draw_arc(p, BEE_RADIUS, 0, TAU, 24, Color.DIM_GRAY, 1.5)
			_text(p + Vector2(8, 4), "?", 13, Color.DIM_GRAY)
		"settled":
			draw_circle(p, BEE_RADIUS * 0.7, c)
		_:
			draw_circle(p, BEE_RADIUS, c)
			draw_arc(p, BEE_RADIUS, 0, TAU, 24, Color(INK, 0.6), 1.0)
			# wings, so a bee reads as a bee
			draw_circle(p + Vector2(-3, -5), 3.0, Color(0.81, 0.9, 0.96, 0.85))
			draw_circle(p + Vector2(3, -5), 3.0, Color(0.81, 0.9, 0.96, 0.85))


func _draw_swarm(it: Dictionary) -> void:
	var p: Vector2 = it.pos
	var settled: bool = it.state == "settled"
	if it.state in ["cluster", "exposed"]:  # the branch it hangs from
		draw_line(p + Vector2(-26, -16), p + Vector2(26, -11), Color("#6f5a45"), 5.0)
	var r := 9.0 if settled else 15.0
	draw_set_transform(p, 0, Vector2(0.8, 1.0))
	draw_circle(Vector2.ZERO, r, BEE_COLORS.honey_bee)
	draw_arc(Vector2.ZERO, r, 0, TAU, 32, Color("#b5523a") if it.state == "exposed" else Color(INK, 0.6),
		3.0 if it.state == "exposed" else 1.0)
	draw_set_transform(Vector2.ZERO)
	for d in [Vector2(-4, -6), Vector2(4, -3), Vector2(-2, 3), Vector2(5, 6), Vector2(-5, 8)]:
		draw_circle(p + d * (r / 15.0), 1.4, Color("#3a2a1a"))
	draw_circle(p + Vector2(0, r * 0.35), 2.5, Color("#5a3d12"))  # the queen
	if settled:
		return
	var k: float = it.population / 1000.0
	var line := "%.1fk · " % k
	match it.state:
		"cluster": line += "%.1f j" % it.days_left + (" · aucune cavité" if it.waiting else "")
		"flying": line += "en vol"
		"exposed": line += "nid à découvert"
	_text(p + Vector2(18, 20), line, 12, Color("#b5523a") if it.state == "exposed" else INK)


# --- view-only interactions -------------------------------------------------------------------------

func _unhandled_input(event: InputEvent) -> void:
	if event is InputEventMouseButton and event.pressed:
		match event.button_index:
			MOUSE_BUTTON_WHEEL_UP: _zoom_at(ZOOM_STEP, event.position)
			MOUSE_BUTTON_WHEEL_DOWN: _zoom_at(1.0 / ZOOM_STEP, event.position)
			MOUSE_BUTTON_LEFT: selected_id = _hovered()  # click selects (or clears) for inspection
	if event is InputEventMouseButton and event.button_index in [MOUSE_BUTTON_RIGHT, MOUSE_BUTTON_MIDDLE]:
		_dragging = event.pressed
	if event is InputEventMouseMotion and (_dragging or event.button_mask & MOUSE_BUTTON_MASK_LEFT):
		camera.position -= event.relative / camera.zoom.x
	if event is InputEventKey and event.pressed:
		match event.keycode:
			KEY_F, KEY_HOME: fit_world()
			KEY_EQUAL, KEY_KP_ADD: _zoom_at(ZOOM_STEP, get_viewport_rect().size / 2)
			KEY_MINUS, KEY_KP_SUBTRACT: _zoom_at(1.0 / ZOOM_STEP, get_viewport_rect().size / 2)
			KEY_ESCAPE: selected_id = ""


func _zoom_at(factor: float, screen_pos: Vector2) -> void:
	var before := get_canvas_transform().affine_inverse() * screen_pos
	camera.zoom = (camera.zoom * factor).clamp(Vector2(0.05, 0.05), Vector2(20, 20))
	camera.force_update_scroll()
	var after := get_canvas_transform().affine_inverse() * screen_pos
	camera.position += before - after


## Id of the entity under the mouse, or "".
func _hovered() -> String:
	var mouse := get_global_mouse_position()
	var best := ""
	var best_d := 18.0 / camera.zoom.x + HABITAT_SIZE / 2
	for it in build_items():
		var d: float = it.pos.distance_to(mouse)
		if d < best_d:
			best = it.id
			best_d = d
	return best


func _find(id: String) -> Dictionary:
	for it in build_items():
		if it.id == id:
			return it
	return {}


func _describe(it: Dictionary) -> String:
	var lines := [it.id]
	match it.kind:
		"habitat":
			lines.append("%s · %d/%d occupé(s)" % [it.type, it.occupants, it.capacity])
		"bee":
			lines.append("%s · %s · %s" % [it.species, it.role, it.state])
		"swarm":
			lines.append("essaim · %d ouvrières · %s" % [it.population, it.state])
			if it.state == "cluster":
				lines.append("%.2f jours restants" % it.days_left)
	if it.get("target_id"):
		lines.append("vol vers %s" % it.target_id)
	if it.get("home_id"):
		lines.append("installé(e) dans %s" % it.home_id)
	if it.has("personality"):
		var p: Dictionary = it.personality
		lines.append("exigence %.2f · audace %.2f · sociabilité %.2f · curiosité %.2f"
			% [p.pickiness, p.boldness, p.sociability, p.curiosity])
	return "\n".join(lines)


func _update_labels() -> void:
	var day_ticks: float = api.config.day_ticks
	var day := int(api.tick / day_ticks) + 1
	var hours := fmod(api.tick, day_ticks) / day_ticks * 24.0
	var counts := {"habitat": 0, "bee": 0, "swarm": 0}
	for e in api.entities.values():
		counts[api._kind(e)] += 1
	hud.text = "Jour %d · %02dh%02d · %s · ×%s · %d habitats, %d abeilles, %d essaims\n%s" % [
		day, int(hours), int(fmod(hours, 1.0) * 60), "en pause" if api.paused else "en cours", api.speed,
		counts.habitat, counts.bee, counts.swarm,
		"Vue seule : agir depuis le tableau de bord · molette = zoom · glisser = déplacer · F = tout voir · clic = détails"]
	var id := selected_id if selected_id else _hovered()
	var it := _find(id) if id else {}
	info.visible = not it.is_empty()
	if info.visible:
		info.text = _describe(it)
		info.position = get_viewport_rect().size - info.get_minimum_size() - Vector2(10, 10)
	empty_message.visible = api.entities.is_empty()
	if empty_message.visible:
		empty_message.position = (get_viewport_rect().size - empty_message.get_minimum_size()) / 2
