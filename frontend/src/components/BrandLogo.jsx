import PropTypes from 'prop-types'
import { BRAND } from '../brand'

export function BrandLogo({ className = 'h-10 w-auto', ...props }) {
  return <img src={BRAND.logoMark} alt="" className={className} {...props} />
}

BrandLogo.propTypes = {
  className: PropTypes.string,
}
