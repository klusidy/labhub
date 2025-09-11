module LabHubClient

export connect, Hub

using HTTP # import Pkg; Pkg.add("HTTP")
using JSON3 # Pkg.add("JSON3")
using URIs # Pkg.add("URIs")

"""
    connect(; host="127.0.0.1", port=8000, scheme="http")

Create a `Hub` connection to the LabHub server.

# Example
```julia
hub = connect(host="127.0.0.1", port=8000)
dev = hub.devices.my_device
shot = dev.data.spectrum.once(n=2048, window="hann")
plt  = dev.plots.spectrum(style="lines")
```
"""
function connect(; host::AbstractString="127.0.0.1", port::Integer=8000, scheme::AbstractString="http")
    base = string(scheme, "://", host, ":", port)
    return Hub(base)
end

# ---------------- Core types ----------------

struct Hub
    base::String
    devices::Dict{String,Any}
end

struct Device
    hub::Hub
    id::String
    name::String
    spec::Any
    data::Dict{String,Any}   # name => DataSource
    plots::Dict{String,Any}  # name => Plot (alias of a DataSource)
end

struct DataSource
    hub::Hub
    dev_id::String
    name::String
    doc::String
    has_plot::Bool
end

# ---------------- HTTP helpers ----------------

function _stringify_params(params::Dict{String,Any})
    Dict(k => string(v) for (k,v) in params)
end

function _get_json(base::String, path::String; params=Dict{String,Any}())
    query_str = isempty(params) ? "" : "?" * join(["$k=$(v)" for (k,v) in _stringify_params(params)], "&")
    url = base * path * query_str
    resp = HTTP.get(url)
    if resp.status ÷ 100 != 2
        error("HTTP $(resp.status) for GET $(url)")
    end
    return JSON3.read(String(resp.body))
end


# ---------------- Hub behavior ----------------

function Hub(base::String)
    h = Hub(base, Dict{String,Any}())
    _refresh!(h)
    return h
end

function _refresh!(hub::Hub)
    devs = _get_json(hub.base, "/api/v1/devices"; params=Dict())
    devices = Dict{String,Any}()
    for d in devs
        id   = String(d["id"])
        name = haskey(d, "name") ? String(d["name"]) : id
        spec = _get_json(hub.base, "/api/v1/devices/$id/spec"; params=Dict())

        data_map  = Dict{String,Any}()
        plots_map = Dict{String,Any}()

        data_specs = haskey(spec, "data_sources") ? spec["data_sources"] :
             (haskey(spec, "data") ? spec["data"] : Any[])
        for ds in data_specs
            dsname    = String(ds["name"])
            dsd       = String(get(ds, "doc", ""))
            has_plot  = Bool(get(ds, "has_plot", false))
            dsp = DataSource(hub, id, dsname, dsd, has_plot)
            data_map[dsname] = dsp
            if has_plot
                plots_map[dsname] = dsp
            end
        end

        devices[name] = Device(hub, id, name, spec, data_map, plots_map)
    end
    d = getfield(hub, :devices)
    empty!(d); merge!(d, devices)
    return hub
end

# ---------------- DataSource API ----------------

function once(ds::DataSource; kwargs...)
    params = Dict{String,Any}(Pair.(string.(keys(kwargs)), collect(values(kwargs))))
    path = "/api/v1/devices/$(ds.dev_id)/data/$(ds.name)"
    return _get_json(ds.hub.base, path; params=params)
end

function plot(ds::DataSource; kwargs...)
    ds.has_plot || throw(ArgumentError("Data source '$(ds.name)' has no plot"))
    params = Dict{String,Any}(Pair.(string.(keys(kwargs)), collect(values(kwargs))))
    path = "/api/v1/devices/$(ds.dev_id)/plots/$(ds.name)"
    return _get_json(ds.hub.base, path; params=params)
end

# ---------------- Discoverability & UX ----------------

Base.propertynames(hub::Hub; private=false) = (:base, :devices)

struct _DevicesNS
    hub::Hub
end

# Devices namespace (dot access) — ALWAYS use the raw Dict on hub
Base.propertynames(ns::_DevicesNS; private=false) = Symbol.(keys(getfield(ns.hub, :devices)))

Base.getproperty(ns::_DevicesNS, s::Symbol) = begin
    # allow internal field access too
    if s === :hub
        return getfield(ns, :hub)
    end
    devs = getfield(ns.hub, :devices)   # <- raw Dict{String,Any}
    return devs[String(s)]              # <- no recursion
end


struct _DataNS
    map::Dict{String,Any}
end
struct _PlotsNS
    map::Dict{String,Any}
end

Base.getproperty(dev::Device, s::Symbol) = begin
    if s === :data
        return _DataNS(getfield(dev, :data))     # raw Dict
    elseif s === :plots
        return _PlotsNS(getfield(dev, :plots))   # raw Dict
    else
        return getfield(dev, s)
    end
end

Base.propertynames(ns::_DataNS; private=false) = Symbol.(keys(ns.map))
Base.propertynames(ns::_PlotsNS; private=false) = Symbol.(keys(ns.map))
Base.getproperty(ns::_DataNS, s::Symbol) = ns.map[String(s)]
Base.getproperty(ns::_PlotsNS, s::Symbol) = ns.map[String(s)]

function Base.show(io::IO, ::MIME"text/plain", hub::Hub)
    println(io, "Hub(", hub.base, ")")
    d = getfield(hub, :devices)                          # raw Dict
    if isempty(d)
        println(io, "  (no devices)")
        return
    end
    println(io, "Devices:")
    for (name, dev) in sort(collect(d); by=first)        # iterate dict
        ndata  = length(getfield(dev, :data))
        nplots = length(getfield(dev, :plots))
        println(io, "  - ", name, "  [data: ", ndata, ", plots: ", nplots, "]")
    end
end



function Base.show(io::IO, ::MIME"text/plain", dev::Device)
    println(io, "Device(", dev.name, ")")
    data_map  = getfield(dev, :data)
    plots_map = getfield(dev, :plots)

    if !isempty(data_map)
        println(io, "Data Sources:")
        for (k, ds_any) in sort(collect(data_map); by=first)
            ds = ds_any::DataSource
            p = ds.has_plot ? " (plot)" : ""
            doc1 = isempty(ds.doc) ? "" : " — " * first(split(ds.doc, '\n'))
            println(io, "  .", k, ".once(; kwargs...) -> Any", p, doc1)
        end
    else
        println(io, "Data Sources: (none)")
    end

    if !isempty(plots_map)
        println(io, "\nPlots:")
        for (k, _) in sort(collect(plots_map); by=first)
            println(io, "  .", k, "(; kwargs...) -> Any")
        end
    end
end


function Base.show(io::IO, ::MIME"text/plain", ds::DataSource)
    plotnote = ds.has_plot ? " (has plot)" : ""
    println(io, "DataSource(", ds.dev_id, ".", ds.name, ")", plotnote)
    if !isempty(ds.doc)
        println(io, ds.doc)
    end
    println(io, "\nUsage:")
    println(io, "  once(ds; kwargs...) -> Any")
    if ds.has_plot
        println(io, "  plot(ds; kwargs...) -> Any")
    end
end

# --- POST helper returning JSON ---
function _post_json(base::String, path::String; body=Dict{String,Any}())
    url = base * path
    resp = HTTP.post(url, ["Content-Type" => "application/json"], JSON3.write(body))
    if resp.status ÷ 100 != 2
        error("HTTP $(resp.status) for POST $(url): $(String(resp.body))")
    end
    return JSON3.read(String(resp.body))
end

# --- Generic command runner ---
function command(dev::Device, name::AbstractString; kwargs...)
    args = Dict{String,Any}(Pair.(string.(keys(kwargs)), collect(values(kwargs))))
    body = Dict("name" => String(name), "args" => args)
    return _post_json(dev.hub.base, "/api/v1/devices/$(dev.id)/commands"; body=body)
end

# --- Convenience wrappers matching your Python example ---
get_timestamps(dev::Device; kwargs...) = command(dev, "get_timestamps"; kwargs...)
start(dev::Device; duration_in_seconds::Integer) = command(dev, "start"; duration_in_seconds=duration_in_seconds)


end # module
