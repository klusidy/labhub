
### Device type ###
struct Device
    doc::String
    dev_id::String # should device know its own name?
    _properties:: Dict{String, DeviceProperty}
    _commands::Dict{String, DeviceCommand}
    _data::Dict{String, DeviceData}
end

function Base.show(io::IO, ::MIME"text/plain", d::Device)
    println(io, d.dev_id, ": ")
    if !isempty(d.doc)
        println(io, "  doc: ", d.doc)
    end
    show(io, MIME"text/plain"(), d.properties)
    #show(io, MIME"text/plain"(), d.commands)
    #show(io, MIME"text/plain"(), d.data)
end


function Base.getproperty(d::Device, name::Symbol)
    if name === :_map
        return getfield(d, :_map)        # real field
    end
    s = String(name)
    if haskey(d._properties, s)
        return d._properties[s]
    elseif haskey(d._commands, s)
        return d._commands[s]
    elseif haskey(d._data, s)
        return d._data[s]
    end
    # fall back to real fields/methods if any
    return getfield(ns, name)  # will throw if not present
end


function Base.propertynames(d::Device; private::Bool=false)
    # only identifiers are valid for dot access; filter others out
    syms = Symbol[]
    for k in keys(d._properties)
        # only include keys that are valid identifiers, so `ns.$k` won’t be a syntax error
        if Base.isidentifier(k)
            push!(syms, Symbol(k))
        end
    end
    for k in keys(d._commands)
        if Base.isidentifier(k)
            push!(syms, Symbol(k))
        end
    end
    for k in keys(d._data)
        if Base.isidentifier(k)
            push!(syms, Symbol(k))
        end
    end
    # also include internal field if private requested
    if private
        return  (:dev_id, :doc, :_properties, :_commands, :_data, syms...) 
    else
        return  (:dev_id, :doc, Tuple(syms))
    end
end

