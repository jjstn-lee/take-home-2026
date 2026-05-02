export default function ProductCard({ product }) {
  const imageUrl = product.image_urls?.[0] || 'https://via.placeholder.com/400x600?text=No+Image'
  const price = product.price?.price || 0
  const originalPrice = product.price?.original_price
  const currency = product.price?.currency || 'USD'
  const isOnSale = originalPrice && originalPrice > price

  return (
    <div className='rounded-lg overflow-hidden bg-card shadow-sm hover:shadow-md transition-shadow'>
      <div className='relative w-full aspect-[3/4] bg-muted overflow-hidden'>
        {isOnSale && (
          <div className='absolute top-3 right-3 z-10 bg-red-500 text-white px-2 py-1 rounded text-xs font-bold'>
            Sale
          </div>
        )}
        <img
          src={imageUrl}
          alt={product.name}
          className='w-full h-full object-cover hover:scale-105 transition-transform duration-300'
        />
      </div>

      <div className='p-3'>
        <h3 className='font-semibold text-sm line-clamp-2'>
          {product.name}
        </h3>
        <p className='text-xs text-muted-foreground line-clamp-1 mt-1'>
          {product.brand}
        </p>
        <div className='mt-2 flex items-center gap-2'>
          <p className='font-bold text-base'>
            {currency} {price.toFixed(2)}
          </p>
          {isOnSale && (
            <p className='text-xs text-muted-foreground line-through'>
              {currency} {originalPrice.toFixed(2)}
            </p>
          )}
        </div>
      </div>
    </div>
  )
}
