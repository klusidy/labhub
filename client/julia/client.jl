# src/LabHubClient.jl
module LabHubClient

include("properties.jl")

include("device.jl")
include("commands.jl")
include("data.jl")

"Simple Hub type — think 'data container' with a field `foo`."
mutable struct Hub
    foo::Any # maybe I'll have use for some other field in the future
    _devices::Dict{String, Device}
end

"Create a Hub (later we’ll add networking here)."
function connect(; foo="hello")

    dummy = Device("A dummy device", "dummy_01", 
                   Dict(
                        "foo" => DeviceProperty("This is fucked up", "foo", 123),
                        "bar" => DeviceProperty("This is beyond repair", "bar", 3.14)
                        ),
                    Dict(), # commands
                    Dict(), # data sources
                    )
    
    devs = Dict("dummy_01" => dummy)
    Hub(foo, devs)
end


function Base.getproperty(h::Hub, name::Symbol)
    if name === :_devices
        return getfield(h, :_devices)   # computed (for now just stored)
    end
    s = String(name)
    if haskey(h._devices, s)
        return h._devices[s]
    end
    return getfield(h, name)
end

"List available properties in tab completion / REPL."
function Base.propertynames(h::Hub; private::Bool=false)
    syms = Symbol[]
    for k in keys(h._devices)
        if Base.isidentifier(k)
            push!(syms, Symbol(k))
        end
    end
    return private ? (:foo, :_devices) : (:foo, Tuple(syms))
end


# Nice REPL display
function Base.show(io::IO, ::MIME"text/plain", h::Hub)
    println(io, "Hub(foo = ", repr(h.foo), ")")
    println(io, "Devices:")
    for (id, device) in h._devices
         println(io, "  .", id, " => ", device.doc)
    end
end

end # module