
### Device type ###
struct DeviceProperty
    doc::String
    name::String
    value::Any
    # type? min/max? unit?
end

function Base.show(io::IO, ::MIME"text/plain", d::DeviceProperty)
    println(io, d.name, ": ", repr(d.value))
    if !isempty(d.doc)
        println(io, "  doc: ", d.doc)
    end
end

# ### NameSpace wrapper around a dict for dot access ###
# struct PropertiesNS
#     _map::Dict{String, _Property}
# end

# Base.getindex(ns::PropertiesNS, k)   = ns._map[k]
# Base.length(ns::PropertiesNS)        = length(ns._map)
# Base.iterate(ns::PropertiesNS, s...) = iterate(ns._map, s...)
# Base.keys(ns::PropertiesNS)          = keys(ns._map)
# Base.haskey(ns::PropertiesNS, k)     = haskey(ns._map, k)

# function Base.getproperty(ns::PropertiesNS, name::Symbol)
#     if name === :_map
#         return getfield(ns, :_map)        # real field
#     end
#     s = String(name)
#     if haskey(ns._map, s)
#         return ns._map[s]
#     end
#     # fall back to real fields/methods if any
#     return getfield(ns, name)  # will throw if not present
# end

# "Expose dot-completable property names for REPL/IDE."
# function Base.propertynames(ns::PropertiesNS; private::Bool=false)
#     # only identifiers are valid for dot access; filter others out
#     syms = Symbol[]
#     for k in keys(ns._map)
#         # only include keys that are valid identifiers, so `ns.$k` won’t be a syntax error
#         if Base.isidentifier(k)
#             push!(syms, Symbol(k))
#         end
#     end
#     # also include internal field if private requested
#     return private ? (:_map, syms...) : Tuple(syms)
# end

# "Pretty print listing similar to the Python client’s 'describe()'"
# function Base.show(io::IO, ::MIME"text/plain", ns::PropertiesNS)
#     println(io, "Properties:")
#     for (id, property) in ns._map
#         println(io, "  .", id, " => ", property.doc)
#     end
# end


