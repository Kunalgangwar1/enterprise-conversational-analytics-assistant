resource "aws_vpc" "application" {
  cidr_block           = var.vpc_cidr
  enable_dns_hostnames = true
  enable_dns_support   = true

  tags = { Name = "${local.name_prefix}-vpc" }
}

resource "aws_internet_gateway" "application" {
  vpc_id = aws_vpc.application.id
  tags   = { Name = "${local.name_prefix}-igw" }
}

resource "aws_subnet" "public" {
  for_each = local.az_map

  vpc_id                  = aws_vpc.application.id
  availability_zone       = each.key
  cidr_block              = cidrsubnet(var.vpc_cidr, 4, each.value)
  map_public_ip_on_launch = false

  tags = { Name = "${local.name_prefix}-public-${each.value + 1}" }
}

resource "aws_subnet" "private_app" {
  for_each = local.az_map

  vpc_id            = aws_vpc.application.id
  availability_zone = each.key
  cidr_block        = cidrsubnet(var.vpc_cidr, 4, each.value + 4)

  tags = { Name = "${local.name_prefix}-private-app-${each.value + 1}" }
}

resource "aws_subnet" "private_data" {
  for_each = local.az_map

  vpc_id            = aws_vpc.application.id
  availability_zone = each.key
  cidr_block        = cidrsubnet(var.vpc_cidr, 4, each.value + 8)

  tags = { Name = "${local.name_prefix}-private-data-${each.value + 1}" }
}

resource "aws_route_table" "public" {
  vpc_id = aws_vpc.application.id
  tags   = { Name = "${local.name_prefix}-public" }
}

resource "aws_route" "public_internet" {
  route_table_id         = aws_route_table.public.id
  destination_cidr_block = "0.0.0.0/0"
  gateway_id             = aws_internet_gateway.application.id
}

resource "aws_route_table_association" "public" {
  for_each = aws_subnet.public

  subnet_id      = each.value.id
  route_table_id = aws_route_table.public.id
}

resource "aws_eip" "nat" {
  count = local.ecs_public_mode ? 0 : 1

  domain = "vpc"
  tags   = { Name = "${local.name_prefix}-nat" }
}

resource "aws_nat_gateway" "application" {
  count = local.ecs_public_mode ? 0 : 1

  allocation_id = aws_eip.nat[0].id
  subnet_id     = values(aws_subnet.public)[0].id

  depends_on = [aws_internet_gateway.application]
  tags       = { Name = "${local.name_prefix}-nat" }
}

resource "aws_route_table" "private_app" {
  vpc_id = aws_vpc.application.id
  tags   = { Name = "${local.name_prefix}-private-app" }
}

resource "aws_route" "private_app_internet" {
  count = local.ecs_public_mode ? 0 : 1

  route_table_id         = aws_route_table.private_app.id
  destination_cidr_block = "0.0.0.0/0"
  nat_gateway_id         = aws_nat_gateway.application[0].id
}

resource "aws_route_table_association" "private_app" {
  for_each = aws_subnet.private_app

  subnet_id      = each.value.id
  route_table_id = aws_route_table.private_app.id
}

resource "aws_route_table" "private_data" {
  vpc_id = aws_vpc.application.id
  tags   = { Name = "${local.name_prefix}-private-data" }
}

resource "aws_route_table_association" "private_data" {
  for_each = aws_subnet.private_data

  subnet_id      = each.value.id
  route_table_id = aws_route_table.private_data.id
}
